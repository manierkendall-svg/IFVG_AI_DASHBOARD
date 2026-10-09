#property copyright "IFVG_AI_EA"
#property version   "1.10"
#property strict

#include <Trade/Trade.mqh>

input string BrainUrl           = "http://127.0.0.1:8080";
input string SharedKey          = "change-me-on-windows";
input string VisionSymbol       = "";
input ENUM_TIMEFRAMES VisionTF  = PERIOD_CURRENT;
input int    LookbackBars       = 120;
input bool   AutoExecute        = false;
input int    HeartbeatSeconds   = 5;
input int    AnalyzeEveryBars   = 1;
input double DefaultLots        = 0.10;
input int    SlippagePoints     = 20;
input string SetupComment       = "FVG/IFVG";
input int    MagicNumber        = 260906;

CTrade trade;
datetime lastBarTime = 0;
datetime lastHeartbeat = 0;
bool     brainPaused = false;
int      lastPingId = 0;

string EffectiveSymbol()
{
   return (VisionSymbol == "" ? _Symbol : VisionSymbol);
}

ENUM_TIMEFRAMES EffectiveTF()
{
   return (VisionTF == PERIOD_CURRENT ? (ENUM_TIMEFRAMES)_Period : VisionTF);
}

string TimeframeName(ENUM_TIMEFRAMES tf)
{
   switch(tf)
   {
      case PERIOD_M1:  return "M1";
      case PERIOD_M5:  return "M5";
      case PERIOD_M15: return "M15";
      case PERIOD_M30: return "M30";
      case PERIOD_H1:  return "H1";
      case PERIOD_H4:  return "H4";
      case PERIOD_D1:  return "D1";
      default:         return EnumToString(tf);
   }
}

string JsonEscape(string text)
{
   string out = text;
   StringReplace(out, "\\", "\\\\");
   StringReplace(out, "\"", "\\\"");
   StringReplace(out, "\n", "\\n");
   StringReplace(out, "\r", "");
   return out;
}

int CountWins()
{
   datetime from = TimeCurrent() - 60 * 60 * 24 * 90;
   HistorySelect(from, TimeCurrent());
   int wins = 0;
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      if((int)HistoryDealGetInteger(ticket, DEAL_MAGIC) != MagicNumber)
         continue;
      if((int)HistoryDealGetInteger(ticket, DEAL_ENTRY) != DEAL_ENTRY_OUT)
         continue;
      if(HistoryDealGetDouble(ticket, DEAL_PROFIT) > 0)
         wins++;
   }
   return wins;
}

int CountLosses()
{
   datetime from = TimeCurrent() - 60 * 60 * 24 * 90;
   HistorySelect(from, TimeCurrent());
   int losses = 0;
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      if((int)HistoryDealGetInteger(ticket, DEAL_MAGIC) != MagicNumber)
         continue;
      if((int)HistoryDealGetInteger(ticket, DEAL_ENTRY) != DEAL_ENTRY_OUT)
         continue;
      if(HistoryDealGetDouble(ticket, DEAL_PROFIT) <= 0)
         losses++;
   }
   return losses;
}

int OpenCount()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if((int)PositionGetInteger(POSITION_MAGIC) == MagicNumber)
         count++;
   }
   return count;
}

double OpenProfit()
{
   double profit = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if((int)PositionGetInteger(POSITION_MAGIC) == MagicNumber)
         profit += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
   }
   return profit;
}

string CandleJson()
{
   ENUM_TIMEFRAMES tf = EffectiveTF();
   string symbol = EffectiveSymbol();
   MqlRates rates[];
   int copied = CopyRates(symbol, tf, 0, LookbackBars, rates);
   if(copied <= 0)
      return "[]";
   ArraySetAsSeries(rates, false);
   string json = "[";
   for(int i = 0; i < copied; i++)
   {
      if(i > 0)
         json += ",";
      json += StringFormat(
         "{\"time\":%I64d,\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%.0f}",
         (long)rates[i].time, rates[i].open, rates[i].high, rates[i].low, rates[i].close, (double)rates[i].tick_volume
      );
   }
   json += "]";
   return json;
}

string SaveChartScreenshot()
{
   string filename = "vision_brain_chart.png";
   if(ChartScreenShot(0, filename, 1280, 720, ALIGN_RIGHT))
      return TerminalInfoString(TERMINAL_DATA_PATH) + "\\MQL5\\Files\\" + filename;
   return "";
}

string HttpPost(string path, string body)
{
   string url = BrainUrl + path;
   char data[];
   char result[];
   string resultHeaders;
   StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);
   ArrayResize(data, ArraySize(data) - 1);
   string headers = "Content-Type: application/json\r\nX-MT5-Key: " + SharedKey + "\r\n";
   ResetLastError();
   int status = WebRequest("POST", url, headers, 8000, data, result, resultHeaders);
   if(status == -1)
   {
      Print("WebRequest failed: ", GetLastError(), " Add ", BrainUrl, " to Tools > Options > Expert Advisors > Allow WebRequest.");
      return "";
   }
   return CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
}

string ExtractJsonString(string json, string key)
{
   string needle = "\"" + key + "\":";
   int pos = StringFind(json, needle);
   if(pos < 0)
      return "";
   pos += StringLen(needle);
   while(pos < StringLen(json) && (StringGetCharacter(json, pos) == ' '))
      pos++;
   if(pos < StringLen(json) && StringGetCharacter(json, pos) == '"')
   {
      pos++;
      int end = StringFind(json, "\"", pos);
      if(end < 0)
         return "";
      return StringSubstr(json, pos, end - pos);
   }
   int end = pos;
   while(end < StringLen(json))
   {
      int ch = StringGetCharacter(json, end);
      if(ch == ',' || ch == '}' || ch == ' ')
         break;
      end++;
   }
   return StringSubstr(json, pos, end - pos);
}

void AckCommand(string id, string action, string okFlag, string detail)
{
   string body = "{";
   body += "\"id\":\"" + JsonEscape(id) + "\",";
   body += "\"action\":\"" + JsonEscape(action) + "\",";
   body += "\"status\":\"done\",";
   body += "\"result\":{\"ok\":" + okFlag + ",\"detail\":\"" + JsonEscape(detail) + "\"}";
   body += "}";
   HttpPost("/mt5/commands/ack", body);
}

void CloseMagicPositions(bool onlyFirst)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != MagicNumber)
         continue;
      trade.PositionClose(ticket);
      if(onlyFirst)
         return;
   }
}

void ExecuteQueuedCommands(string response)
{
   int search = 0;
   while(true)
   {
      int actionPos = StringFind(response, "\"action\":", search);
      if(actionPos < 0)
         break;
      string action = ExtractJsonString(StringSubstr(response, actionPos - 20), "action");
      if(action == "")
         action = ExtractJsonString(StringSubstr(response, actionPos), "action");
      int idPos = StringFind(response, "\"id\":", MathMax(0, actionPos - 80));
      string id = "";
      if(idPos >= 0)
         id = ExtractJsonString(StringSubstr(response, idPos), "id");
      if(action == "ping")
      {
         lastPingId++;
         AckCommand(id, action, "true", "pong");
      }
      else if(action == "pause")
      {
         brainPaused = true;
         AckCommand(id, action, "true", "paused");
      }
      else if(action == "resume")
      {
         brainPaused = false;
         AckCommand(id, action, "true", "resumed");
      }
      else if(action == "open_trade")
      {
         string direction = ExtractJsonString(StringSubstr(response, actionPos), "direction");
         if(direction == "")
            direction = "buy";
         if(direction == "buy" || direction == "long")
            trade.Buy(DefaultLots, EffectiveSymbol());
         else
            trade.Sell(DefaultLots, EffectiveSymbol());
         AckCommand(id, action, "true", direction);
      }
      else if(action == "close_trade")
      {
         CloseMagicPositions(true);
         AckCommand(id, action, "true", "closed one");
      }
      else if(action == "close_all")
      {
         CloseMagicPositions(false);
         AckCommand(id, action, "true", "closed all");
      }
      search = actionPos + 8;
      if(search >= StringLen(response))
         break;
   }
}

string HeartbeatBody()
{
   string symbol = EffectiveSymbol();
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   string body = "{";
   body += "\"symbol\":\"" + symbol + "\",";
   body += "\"timeframe\":\"" + TimeframeName(EffectiveTF()) + "\",";
   body += "\"bid\":" + DoubleToString(bid, 5) + ",";
   body += "\"ask\":" + DoubleToString(ask, 5) + ",";
   body += "\"price\":" + DoubleToString((bid + ask) / 2.0, 5) + ",";
   body += "\"balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + ",";
   body += "\"equity\":" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2) + ",";
   body += "\"margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN), 2) + ",";
   body += "\"profit\":" + DoubleToString(OpenProfit(), 2) + ",";
   body += "\"open_positions\":" + IntegerToString(OpenCount()) + ",";
   body += "\"trades_won\":" + IntegerToString(CountWins()) + ",";
   body += "\"trades_lost\":" + IntegerToString(CountLosses()) + ",";
   body += "\"currency\":\"" + AccountInfoString(ACCOUNT_CURRENCY) + "\",";
   body += "\"account\":\"" + IntegerToString((int)AccountInfoInteger(ACCOUNT_LOGIN)) + "\",";
   body += "\"pong\":true";
   body += "}";
   return body;
}

void SendHeartbeat()
{
   string response = HttpPost("/mt5/heartbeat", HeartbeatBody());
   string paused = ExtractJsonString(response, "paused");
   if(paused == "true")
      brainPaused = true;
   if(paused == "false")
      brainPaused = false;
   ExecuteQueuedCommands(response);
   lastHeartbeat = TimeCurrent();
}

void MaybeExecute(string action, string direction)
{
   if(!AutoExecute || action != "ACCEPT" || brainPaused)
      return;
   trade.SetDeviationInPoints(SlippagePoints);
   if(direction == "buy" || direction == "long")
      trade.Buy(DefaultLots, EffectiveSymbol());
   else if(direction == "sell" || direction == "short")
      trade.Sell(DefaultLots, EffectiveSymbol());
}

void AnalyzeLiveBar()
{
   string screenshot = SaveChartScreenshot();
   string direction = "";
   double bid = SymbolInfoDouble(EffectiveSymbol(), SYMBOL_BID);
   double ask = SymbolInfoDouble(EffectiveSymbol(), SYMBOL_ASK);
   double close1 = iClose(EffectiveSymbol(), EffectiveTF(), 1);
   double close2 = iClose(EffectiveSymbol(), EffectiveTF(), 2);
   if(close1 > close2)
      direction = "buy";
   else if(close1 < close2)
      direction = "sell";

   string body = "{";
   body += "\"symbol\":\"" + EffectiveSymbol() + "\",";
   body += "\"timeframe\":\"" + TimeframeName(EffectiveTF()) + "\",";
   body += "\"direction\":\"" + direction + "\",";
   body += "\"entry\":" + DoubleToString((bid + ask) / 2.0, 5) + ",";
   body += "\"comment\":\"" + JsonEscape(SetupComment) + "\",";
   body += "\"screenshot\":\"" + JsonEscape(screenshot) + "\",";
   body += "\"candles\":" + CandleJson();
   body += "}";

   string response = HttpPost("/mt5/analyze", body);
   string action = ExtractJsonString(response, "action");
   string reason = ExtractJsonString(response, "reason");
   Comment("IFVG_AI_EA: ", action, "\n", reason);
   Print("IFVG_AI_EA ", action, " ", reason);
   MaybeExecute(action, direction);
}

int OnInit()
{
   trade.SetExpertMagicNumber(MagicNumber);
   EventSetTimer(HeartbeatSeconds);
   SendHeartbeat();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   SendHeartbeat();
}

void OnTick()
{
   datetime barTime = iTime(EffectiveSymbol(), EffectiveTF(), 0);
   if(barTime == 0)
      return;
   if(lastBarTime == 0)
      lastBarTime = barTime;
   if(barTime != lastBarTime)
   {
      lastBarTime = barTime;
      if(AnalyzeEveryBars >= 1)
         AnalyzeLiveBar();
   }
}
