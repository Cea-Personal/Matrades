//+------------------------------------------------------------------+
//| MatradesMT5BridgeEA.mq5                                          |
//| Read-only MT5 connector for the Matrades bridge.                 |
//|                                                                  |
//| MT5 exposes outbound WebRequest from an EA, but does not expose a  |
//| native TCP listener.  This EA therefore publishes signed snapshots |
//| to the Python bridge, which serves Matrades' read-only API.        |
//+------------------------------------------------------------------+
#property copyright "Matrades"
#property link      "https://github.com/matrades"
#property version   "1.0.0"
#property strict
#property description "Read-only MT5 snapshot publisher for Matrades"
#property description "Add the bridge URL to Tools > Options > Expert Advisors > Allow WebRequest"

input string InpBridgeUrl = "http://127.0.0.1:8765";
input string InpBridgeSecret = "";
input string InpMatradesAccountId = "";
input string InpAccountReference = "";
input int    InpPublishSeconds = 5;
input int    InpRequestTimeoutMs = 5000;

ulong g_sequence = 0;

string BaseUrl()
  {
   string value=InpBridgeUrl;
   while(StringLen(value)>0 && StringSubstr(value,StringLen(value)-1,1)=="/")
      value=StringSubstr(value,0,StringLen(value)-1);
   return(value);
  }

string JsonEscape(string value)
  {
   StringReplace(value,"\\","\\\\");
   StringReplace(value,"\"","\\\"");
   StringReplace(value,"\r","\\r");
   StringReplace(value,"\n","\\n");
   return(value);
  }

string IsoTime(datetime value)
  {
   MqlDateTime parts;
   TimeToStruct(value,parts);
   return(StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ",
                       parts.year,parts.mon,parts.day,
                       parts.hour,parts.min,parts.sec));
  }

int StringBytes(const string value,uchar &output[])
  {
   int length=StringLen(value);
   ArrayResize(output,length);
   if(length==0)
      return(0);
   StringToCharArray(value,output,0,length,CP_UTF8);
   return(length);
  }

string Hex(const uchar &value[])
  {
   string result="";
   for(int index=0;index<ArraySize(value);index++)
      result+=StringFormat("%02x",(int)value[index]);
   return(result);
  }

string HmacSha256(const string message,const string secret)
  {
   uchar key[];
   uchar message_bytes[];
   uchar empty_key[];
   StringBytes(secret,key);
   StringBytes(message,message_bytes);

   // SHA-256 HMAC uses a 64-byte block.  Hash keys longer than the block.
   if(ArraySize(key)>64)
     {
      uchar hashed_key[];
      CryptEncode(CRYPT_HASH_SHA256,key,empty_key,hashed_key);
      ArrayResize(key,ArraySize(hashed_key));
      ArrayCopy(key,hashed_key);
     }

   uchar padded_key[];
   ArrayResize(padded_key,64);
   ArrayInitialize(padded_key,0);
   int key_length=ArraySize(key);
   if(key_length>64)
      key_length=64;
   ArrayCopy(padded_key,key,0,0,key_length);

   uchar ipad[];
   uchar opad[];
   ArrayResize(ipad,64);
   ArrayResize(opad,64);
   for(int index=0;index<64;index++)
     {
      ipad[index]=(uchar)(padded_key[index]^0x36);
      opad[index]=(uchar)(padded_key[index]^0x5c);
     }

   uchar inner_data[];
   ArrayResize(inner_data,64+ArraySize(message_bytes));
   ArrayCopy(inner_data,ipad,0,0,64);
   ArrayCopy(inner_data,message_bytes,64,0,ArraySize(message_bytes));
   uchar inner_hash[];
   CryptEncode(CRYPT_HASH_SHA256,inner_data,empty_key,inner_hash);

   uchar outer_data[];
   ArrayResize(outer_data,64+ArraySize(inner_hash));
   ArrayCopy(outer_data,opad,0,0,64);
   ArrayCopy(outer_data,inner_hash,64,0,ArraySize(inner_hash));
   uchar final_hash[];
   CryptEncode(CRYPT_HASH_SHA256,outer_data,empty_key,final_hash);
   return(Hex(final_hash));
  }

string NewNonce()
  {
   // Keep all numeric-to-text conversions explicit.  IntegerToString accepts
   // MQL5's 64-bit integer type and avoids vararg format-type mismatches.
   return(IntegerToString((long)GetTickCount())+"-"+
          IntegerToString((long)MathRand())+"-"+
          IntegerToString((long)GetTickCount()));
  }

string MessageId()
  {
   // MQL5 uses IntegerToString for both 32-bit and 64-bit integer values.
   string tail=IntegerToString((long)GetTickCount())+IntegerToString((long)g_sequence);
   while(StringLen(tail)<12)
      tail="0"+tail;
   if(StringLen(tail)>12)
      tail=StringSubstr(tail,StringLen(tail)-12);
   return("00000000-0000-4000-8000-"+tail);
  }

double RealizedDailyPnl()
  {
   datetime now=TimeCurrent();
   MqlDateTime parts;
   TimeToStruct(now,parts);
   parts.hour=0;
   parts.min=0;
   parts.sec=0;
   datetime start=StructToTime(parts);
   if(!HistorySelect(start,now))
      return(0.0);

   double total=0.0;
   int count=HistoryDealsTotal();
   for(int index=0;index<count;index++)
     {
      ulong ticket=HistoryDealGetTicket(index);
      if(ticket==0)
         continue;
      long entry=HistoryDealGetInteger(ticket,DEAL_ENTRY);
      if(entry!=DEAL_ENTRY_OUT && entry!=DEAL_ENTRY_OUT_BY && entry!=DEAL_ENTRY_INOUT)
         continue;
      total+=HistoryDealGetDouble(ticket,DEAL_PROFIT);
      total+=HistoryDealGetDouble(ticket,DEAL_SWAP);
      total+=HistoryDealGetDouble(ticket,DEAL_COMMISSION);
      total+=HistoryDealGetDouble(ticket,DEAL_FEE);
     }
   return(total);
  }

string PositionsJson()
  {
   string result="[";
   bool first=true;
   int count=PositionsTotal();
   for(int index=0;index<count;index++)
     {
      ulong ticket=PositionGetTicket(index);
      if(ticket==0 || !PositionSelectByTicket(ticket))
         continue;
      if(!first)
         result+=",";
      first=false;
      long position_type=PositionGetInteger(POSITION_TYPE);
      string direction=position_type==POSITION_TYPE_BUY ? "BUY" : "SELL";
      string symbol=PositionGetString(POSITION_SYMBOL);
      double stop_loss=PositionGetDouble(POSITION_SL);
      double take_profit=PositionGetDouble(POSITION_TP);
      result+="{\"position_id\":\""+IntegerToString((long)PositionGetInteger(POSITION_IDENTIFIER))+"\"";
      result+=",\"account_id\":\""+JsonEscape(InpMatradesAccountId)+"\"";
      result+=",\"symbol\":\""+JsonEscape(symbol)+"\"";
      result+=",\"direction\":\""+direction+"\"";
      result+=",\"volume\":"+DoubleToString(PositionGetDouble(POSITION_VOLUME),8);
      result+=",\"entry_price\":"+DoubleToString(PositionGetDouble(POSITION_PRICE_OPEN),8);
      result+=",\"stop_loss\":"+DoubleToString(stop_loss,8);
      result+=",\"take_profit\":"+DoubleToString(take_profit,8);
      result+=",\"pnl\":"+DoubleToString(PositionGetDouble(POSITION_PROFIT),8);
      result+=",\"fees\":0";
      result+=",\"opened_at\":\""+IsoTime((datetime)PositionGetInteger(POSITION_TIME))+"\"";
      result+=",\"observed_at\":\""+IsoTime(TimeGMT())+"\"}";
     }
   result+="]";
   return(result);
  }

string SnapshotJson()
  {
   g_sequence++;
   string body="{";
   body+="\"message_id\":\""+MessageId()+"\"";
   body+=",\"account_id\":\""+JsonEscape(InpMatradesAccountId)+"\"";
   body+=",\"sequence\":"+IntegerToString((long)g_sequence);
   body+=",\"observed_at\":\""+IsoTime(TimeGMT())+"\"";
   body+=",\"balance\":"+DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),8);
   body+=",\"equity\":"+DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),8);
   body+=",\"realized_daily_pnl\":"+DoubleToString(RealizedDailyPnl(),8);
   body+=",\"positions\":"+PositionsJson();
   body+=",\"signature\":\"ea-published-over-authenticated-channel\"}";
   return(body);
  }

bool PublishSnapshot()
  {
   if(StringLen(InpBridgeSecret)==0 || StringLen(InpMatradesAccountId)==0)
      return(false);
   string body=SnapshotJson();
   string timestamp=IntegerToString((long)TimeGMT());
   string nonce=NewNonce();
   string signed_message=timestamp+"."+nonce+"."+body;
   string signature=HmacSha256(signed_message,InpBridgeSecret);
   string headers="Content-Type: application/json\r\n"+
                  "X-Timestamp: "+timestamp+"\r\n"+
                  "X-Nonce: "+nonce+"\r\n"+
                  "X-Signature: "+signature+"\r\n";
   uchar request_bytes[];
   char request_data[];
   char response_data[];
   StringBytes(body,request_bytes);
   ArrayResize(request_data,ArraySize(request_bytes));
   for(int index=0;index<ArraySize(request_bytes);index++)
      request_data[index]=(char)request_bytes[index];
   string response_headers="";
   int status=WebRequest("POST",BaseUrl()+"/ingest",headers,InpRequestTimeoutMs,
                         request_data,response_data,response_headers);
   if(status!=200)
     {
      PrintFormat("Matrades bridge publish failed: HTTP %d, error %d",status,GetLastError());
      return(false);
     }
   return(true);
  }

int OnInit()
  {
   if(StringLen(InpBridgeSecret)==0)
     {
      Print("Matrades bridge: set InpBridgeSecret to the same secret configured in Matrades.");
      return(INIT_PARAMETERS_INCORRECT);
     }
   if(StringLen(InpMatradesAccountId)==0)
     {
      Print("Matrades bridge: set InpMatradesAccountId to the UUID of the Matrades trading account.");
      return(INIT_PARAMETERS_INCORRECT);
     }
   if(StringLen(InpAccountReference)>0 &&
      InpAccountReference!=IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN)))
     {
      PrintFormat("Matrades bridge: broker login %s does not match InpAccountReference %s",
                  IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN)),InpAccountReference);
      return(INIT_PARAMETERS_INCORRECT);
     }
   if(InpPublishSeconds<1)
      return(INIT_PARAMETERS_INCORRECT);
   MathSrand((int)GetTickCount());
   EventSetTimer(InpPublishSeconds);
   PublishSnapshot();
   PrintFormat("Matrades MT5 bridge EA started for account %s",InpMatradesAccountId);
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
  }

void OnTimer()
  {
   if(!TerminalInfoInteger(TERMINAL_CONNECTED))
      return;
   PublishSnapshot();
  }

void OnTick()
  {
  }
//+------------------------------------------------------------------+
