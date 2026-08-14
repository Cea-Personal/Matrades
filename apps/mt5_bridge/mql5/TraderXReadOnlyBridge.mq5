//+------------------------------------------------------------------+
//|                                           TraderXReadOnlyBridge |
//| An outbound evidence-only Expert Advisor for MetaTrader 5.      |
//| It contains no trade class, order API, or account mutation.     |
//+------------------------------------------------------------------+
#property copyright "TraderX"
#property version   "1.0"
#property strict

input string TraderXApiUrl = "";       // e.g. https://traderx.example.com/api/v1
input string AgentId = "";             // shown by TraderX Command Center
input string EnrollmentCode = "";      // one-time code; cleared after enrollment
input int    PollSeconds = 15;

string g_agent_token = "";
string g_agent_id = "";
string g_api_url = "";
string g_state_file = "";

// MQL5 WebRequest requires this API origin in Tools > Options > Expert Advisors > Allow WebRequest.
// The EA calls only these fixed outbound POST endpoints:
//   /integrations/mt5/agents/{agentId}/configuration
//   /integrations/mt5/agents/{agentId}/enroll
//   /integrations/mt5/agents/{agentId}/snapshots

int OnInit()
  {
   if(StringFind(TraderXApiUrl,"https://")!=0 || StringLen(AgentId)==0)
     {
      Print("TraderX bridge requires an HTTPS API URL and AgentId.");
      return(INIT_PARAMETERS_INCORRECT);
     }
   if(PollSeconds<5)
     {
      Print("TraderX bridge polling must be at least five seconds.");
      return(INIT_PARAMETERS_INCORRECT);
     }

   g_api_url=TrimTrailingSlash(TraderXApiUrl);
   g_agent_id=AgentId;
   g_state_file="TraderXReadOnlyBridge-"+g_agent_id+".dat";
   // A newly supplied one-time code always wins over a previously saved
   // credential. This makes renewal recover from an invalidated local token
   // without asking the trader to find and delete an MT5 sandbox file.
   if(StringLen(EnrollmentCode)>=32)
     {
      if(!Enroll())
         return(INIT_FAILED);
     }
   else if(!LoadState())
     {
      Print("Paste the one-time enrollment code from TraderX Command Center into EA inputs.");
      return(INIT_PARAMETERS_INCORRECT);
     }
   EventSetTimer(PollSeconds);
   SendSnapshot();
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
  }

void OnTimer()
  {
   SendSnapshot();
  }

bool Enroll()
  {
   string configuration;
   if(!PostJson("configuration", "{\"enrollment_code\":\""+JsonString(EnrollmentCode)+"\"}", "", configuration))
      return(false);
   string expected_login=JsonStringValue(configuration,"login");
   string expected_server=JsonStringValue(configuration,"server");
   if(expected_login!=IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN)) || expected_server!=AccountInfoString(ACCOUNT_SERVER))
     {
      Print("TraderX enrollment does not match the MT5 account currently signed in.");
      return(false);
     }
   string response;
   if(!PostJson("enroll", "{\"enrollment_code\":\""+JsonString(EnrollmentCode)+"\","+TerminalPayload()+"}", "", response))
      return(false);
   g_agent_token=JsonStringValue(response,"agent_token");
   if(StringLen(g_agent_token)==0)
     {
      Print("TraderX did not return an agent credential.");
      return(false);
     }
   if(!SaveState())
      return(false);
   Print("TraderX read-only bridge enrolled. Remove the one-time code from EA inputs now.");
   return(true);
  }

void SendSnapshot()
  {
   if(!TerminalEvidenceSafe())
     {
      Print("TraderX bridge did not send data: MT5 is disconnected or trading is permitted.");
      return;
     }
   string response;
   string snapshot=SnapshotPayload();
   if(StringLen(snapshot)>0 && PostJson("snapshots", snapshot, "Bearer "+g_agent_token, response))
      Print("TraderX accepted a read-only MT5 snapshot.");
  }

bool TerminalEvidenceSafe()
  {
   return(
      (bool)TerminalInfoInteger(TERMINAL_CONNECTED)
      && !(bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)
      && !(bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)
   );
  }

string SnapshotPayload()
  {
   datetime now=TimeCurrent();
   datetime from=now-172800;
   if(!HistorySelect(from,now))
     {
      Print("TraderX bridge could not read MT5 deal history. Error ",GetLastError());
      return("");
     }
   return("{"+TerminalPayload()+","+
          "\"balance\":\""+DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2)+"\","+
          "\"equity\":\""+DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2)+"\","+
          "\"currency\":\""+JsonString(AccountInfoString(ACCOUNT_CURRENCY))+"\","+
          "\"positions\":"+PositionsJson()+","+
          "\"deals\":"+DealsJson()+","+
          "\"instruments\":"+InstrumentsJson()+"}");
  }

string TerminalPayload()
  {
   return("\"connected\":"+JsonBool((bool)TerminalInfoInteger(TERMINAL_CONNECTED))+","+
          "\"trading_disabled\":"+JsonBool(TerminalEvidenceSafe())+","+
          "\"login\":\""+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))+"\","+
          "\"server\":\""+JsonString(AccountInfoString(ACCOUNT_SERVER))+"\","+
          "\"terminal_version\":\""+IntegerToString((int)TerminalInfoInteger(TERMINAL_BUILD))+"\"");
  }

string PositionsJson()
  {
   string result="[";
   for(int index=0;index<PositionsTotal();index++)
     {
      ulong ticket=PositionGetTicket(index);
      if(ticket==0)
        continue;
      if(StringLen(result)>1)
         result+=",";
      result+="{"+
              "\"ticket\":\""+IntegerToString((long)ticket)+"\","+
              "\"identifier\":\""+IntegerToString(PositionGetInteger(POSITION_IDENTIFIER))+"\","+
              "\"symbol\":\""+JsonString(PositionGetString(POSITION_SYMBOL))+"\","+
              "\"type\":"+IntegerToString(PositionGetInteger(POSITION_TYPE))+","+
              "\"volume\":\""+DoubleToString(PositionGetDouble(POSITION_VOLUME),2)+"\","+
              "\"price_open\":\""+DoubleToString(PositionGetDouble(POSITION_PRICE_OPEN),Digits())+"\","+
              "\"price_current\":\""+DoubleToString(PositionGetDouble(POSITION_PRICE_CURRENT),Digits())+"\","+
              "\"stop_loss\":\""+DoubleToString(PositionGetDouble(POSITION_SL),Digits())+"\","+
              "\"take_profit\":\""+DoubleToString(PositionGetDouble(POSITION_TP),Digits())+"\","+
              "\"profit\":\""+DoubleToString(PositionGetDouble(POSITION_PROFIT),2)+"\","+
              "\"time_msc\":\""+IntegerToString(PositionGetInteger(POSITION_TIME_MSC))+"\"}";
     }
   return(result+"]");
  }

string DealsJson()
  {
   string result="[";
   int total=HistoryDealsTotal();
   for(int index=0;index<total;index++)
     {
      ulong ticket=HistoryDealGetTicket(index);
      if(ticket==0)
        continue;
      if(StringLen(result)>1)
         result+=",";
      result+="{"+
              "\"ticket\":\""+IntegerToString((long)ticket)+"\","+
              "\"position_id\":\""+IntegerToString(HistoryDealGetInteger(ticket,DEAL_POSITION_ID))+"\","+
              "\"symbol\":\""+JsonString(HistoryDealGetString(ticket,DEAL_SYMBOL))+"\","+
              "\"type\":"+IntegerToString(HistoryDealGetInteger(ticket,DEAL_TYPE))+","+
              "\"volume\":\""+DoubleToString(HistoryDealGetDouble(ticket,DEAL_VOLUME),2)+"\","+
              "\"price\":\""+DoubleToString(HistoryDealGetDouble(ticket,DEAL_PRICE),Digits())+"\","+
              "\"profit\":\""+DoubleToString(HistoryDealGetDouble(ticket,DEAL_PROFIT),2)+"\","+
              "\"time_msc\":\""+IntegerToString(HistoryDealGetInteger(ticket,DEAL_TIME_MSC))+"\"}";
     }
   return(result+"]");
  }

string InstrumentsJson()
  {
   string result="[";
   // Read the terminal's visible broker universe. Historical reads are evidence-only and
   // never select a symbol, alter Market Watch, or invoke a trading operation.
   int total=SymbolsTotal(true);
   for(int index=0;index<total;index++)
     {
      string symbol=SymbolName(index,true);
      if(StringLen(symbol)==0)
         continue;
      int digits=(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS);
      if(StringLen(result)>1)
         result+=",";
      result+="{\"symbol\":\""+JsonString(symbol)+"\","+
              "\"description\":\""+JsonString(SymbolInfoString(symbol,SYMBOL_DESCRIPTION))+"\","+
              "\"path\":\""+JsonString(SymbolInfoString(symbol,SYMBOL_PATH))+"\","+
              "\"currency_base\":\""+JsonString(SymbolInfoString(symbol,SYMBOL_CURRENCY_BASE))+"\","+
              "\"currency_profit\":\""+JsonString(SymbolInfoString(symbol,SYMBOL_CURRENCY_PROFIT))+"\","+
              "\"digits\":"+IntegerToString(digits)+","+
              "\"trade_mode\":"+IntegerToString((int)SymbolInfoInteger(symbol,SYMBOL_TRADE_MODE))+","+
              "\"bid\":\""+DoubleToString(SymbolInfoDouble(symbol,SYMBOL_BID),digits)+"\","+
              "\"ask\":\""+DoubleToString(SymbolInfoDouble(symbol,SYMBOL_ASK),digits)+"\","+
              "\"contract_size\":\""+DoubleToString(SymbolInfoDouble(symbol,SYMBOL_TRADE_CONTRACT_SIZE),2)+"\","+
              "\"tick_size\":\""+DoubleToString(SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE),digits)+"\","+
              "\"tick_value\":\""+DoubleToString(SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_VALUE),8)+"\","+
              "\"volume_min\":\""+DoubleToString(SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN),2)+"\","+
              "\"volume_max\":\""+DoubleToString(SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX),2)+"\","+
              "\"volume_step\":\""+DoubleToString(SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP),2)+"\","+
              "\"closes\":"+CloseSeriesJson(symbol,digits)+","+
              "\"tick_volumes\":"+TickVolumeSeriesJson(symbol)+"}";
     }
   return(result+"]");
  }

string CloseSeriesJson(const string symbol,const int digits)
  {
   double values[];
   int copied=CopyClose(symbol,PERIOD_H1,1,400,values);
   if(copied<400)
      return("[]");
   string result="[";
   for(int index=0;index<copied;index++)
     {
      if(index>0)
         result+=",";
      result+="\""+DoubleToString(values[index],digits)+"\"";
     }
   return(result+"]");
  }

string TickVolumeSeriesJson(const string symbol)
  {
   long values[];
   int copied=CopyTickVolume(symbol,PERIOD_H1,1,400,values);
   if(copied<400)
      return("[]");
   string result="[";
   for(int index=0;index<copied;index++)
     {
      if(index>0)
         result+=",";
      result+=IntegerToString(values[index]);
     }
   return(result+"]");
  }

bool PostJson(const string operation,const string payload,const string authorization,string &response)
  {
   if(StringLen(payload)==0)
      return(false);
   string url=g_api_url+"/integrations/mt5/agents/"+g_agent_id+"/"+operation;
   string headers="Content-Type: application/json\r\nAccept: application/json";
   if(StringLen(authorization)>0)
      headers+="\r\nAuthorization: "+authorization;
   char data[],result[];
   string result_headers;
   StringToCharArray(payload,data,0,WHOLE_ARRAY,CP_UTF8);
   ArrayResize(data,ArraySize(data)-1);
   ResetLastError();
   int status=WebRequest("POST",url,headers,15000,data,result,result_headers);
   response=CharArrayToString(result,0,ArraySize(result),CP_UTF8);
   if(status<200 || status>=300)
     {
      Print("TraderX bridge request failed. HTTP ",status," MT5 error ",GetLastError(),". ",StringSubstr(response,0,500));
      return(false);
     }
   return(true);
  }

bool LoadState()
  {
   int handle=FileOpen(g_state_file,FILE_READ|FILE_BIN);
   if(handle==INVALID_HANDLE)
      return(false);
   g_agent_token=FileReadString(handle);
   FileClose(handle);
   return(StringLen(g_agent_token)>0);
  }

bool SaveState()
  {
   int handle=FileOpen(g_state_file,FILE_WRITE|FILE_BIN);
   if(handle==INVALID_HANDLE)
     {
      Print("TraderX bridge could not store its local credential. Error ",GetLastError());
      return(false);
     }
   FileWriteString(handle,g_agent_token);
   FileClose(handle);
   return(true);
  }

string TrimTrailingSlash(string value)
  {
   while(StringLen(value)>0 && StringGetCharacter(value,StringLen(value)-1)=='/')
      value=StringSubstr(value,0,StringLen(value)-1);
   return(value);
  }

string JsonString(string value)
  {
   StringReplace(value,"\\","\\\\");
   StringReplace(value,"\"","\\\"");
   StringReplace(value,"\r","\\r");
   StringReplace(value,"\n","\\n");
   return(value);
  }

string JsonBool(const bool value)
  {
   return(value ? "true" : "false");
  }

string JsonStringValue(const string json,const string key)
  {
   string marker="\""+key+"\":\"";
   int start=StringFind(json,marker);
   if(start<0)
      return("");
   start+=StringLen(marker);
   int finish=StringFind(json,"\"",start);
   if(finish<0)
      return("");
   return(StringSubstr(json,start,finish-start));
  }
