//+------------------------------------------------------------------+
//| MatradesMT5BridgeEA.mq5                                          |
//| Autonomous MT5 connector for the Matrades bridge.               |
//|                                                                  |
//| MT5 exposes outbound WebRequest from an EA, but does not expose a  |
//| native TCP listener.  This EA therefore publishes signed snapshots |
//| to the Python bridge, which serves Matrades' read-only API.        |
//+------------------------------------------------------------------+
#property copyright "Matrades"
#property link      "https://github.com/matrades"
#property version   "1.100"
#property strict
#property description "MT5 snapshot publisher and bounded command executor for Matrades"
#property description "Add the bridge URL to Tools > Options > Expert Advisors > Allow WebRequest"

input string InpBridgeUrl = "http://127.0.0.1:8765";
input string InpBridgeSecret = "";
input string InpMatradesAccountId = "";
input string InpAccountReference = "";
input int    InpPublishSeconds = 5;
input int    InpRequestTimeoutMs = 5000;
input int    InpMarketDataPublishSeconds = 60;
input int    InpResearchCandleCount = 100;
input int    InpMaxResearchMetalSymbols = 20;

ulong g_sequence = 0;
ulong g_market_data_sequence = 0;
datetime g_last_market_data_publish = 0;
string g_processed_command_ids[];
int g_last_publish_status = 0;
int g_last_publish_error = 0;

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

bool IsMetalSymbol(string symbol)
  {
   string searchable=symbol+" "+SymbolInfoString(symbol,SYMBOL_PATH)+" "+
                     SymbolInfoString(symbol,SYMBOL_DESCRIPTION);
   StringToUpper(searchable);
   return(StringFind(searchable,"XAU")>=0 || StringFind(searchable,"XAG")>=0 ||
          StringFind(searchable,"GOLD")>=0 || StringFind(searchable,"SILVER")>=0);
  }

string CandlesJson(string symbol)
  {
   MqlRates rates[];
   int requested=InpResearchCandleCount;
   if(requested<3)
      requested=3;
   if(requested>500)
      requested=500;
   int copied=CopyRates(symbol,PERIOD_H1,0,requested,rates);
   if(copied<3)
      return("[]");
   string result="[";
   for(int index=0;index<copied;index++)
     {
      if(index>0)
         result+=",";
      result+="{\"observed_at\":\""+IsoTime(rates[index].time)+"\"";
      result+=",\"open\":"+DoubleToString(rates[index].open,8);
      result+=",\"high\":"+DoubleToString(rates[index].high,8);
      result+=",\"low\":"+DoubleToString(rates[index].low,8);
      result+=",\"close\":"+DoubleToString(rates[index].close,8);
      result+=",\"tick_volume\":"+IntegerToString((long)rates[index].tick_volume)+"}";
     }
   result+="]";
   return(result);
  }

string MetalInstrumentsJson()
  {
   string result="[";
   int accepted=0;
   int total=SymbolsTotal(false);
   int maximum=InpMaxResearchMetalSymbols;
   if(maximum<1)
      maximum=1;
   if(maximum>50)
      maximum=50;
   for(int index=0;index<total && accepted<maximum;index++)
     {
      string symbol=SymbolName(index,false);
      if(StringLen(symbol)==0 || !IsMetalSymbol(symbol) || !SymbolSelect(symbol,true))
         continue;
      double bid=SymbolInfoDouble(symbol,SYMBOL_BID);
      double ask=SymbolInfoDouble(symbol,SYMBOL_ASK);
      double contract_size=SymbolInfoDouble(symbol,SYMBOL_TRADE_CONTRACT_SIZE);
      double tick_size=SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE);
      double volume_min=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
      double volume_max=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);
      double volume_step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
      string candles=CandlesJson(symbol);
      if(bid<=0.0 || ask<=0.0 || contract_size<=0.0 || tick_size<=0.0 ||
         volume_min<=0.0 || volume_max<=0.0 || volume_step<=0.0 || candles=="[]")
         continue;
      if(accepted>0)
         result+=",";
      result+="{\"symbol\":\""+JsonEscape(symbol)+"\"";
      result+=",\"path\":\""+JsonEscape(SymbolInfoString(symbol,SYMBOL_PATH))+"\"";
      result+=",\"description\":\""+JsonEscape(SymbolInfoString(symbol,SYMBOL_DESCRIPTION))+"\"";
      result+=",\"bid\":"+DoubleToString(bid,8);
      result+=",\"ask\":"+DoubleToString(ask,8);
      result+=",\"digits\":"+IntegerToString((long)SymbolInfoInteger(symbol,SYMBOL_DIGITS));
      result+=",\"trade_contract_size\":"+DoubleToString(contract_size,8);
      result+=",\"trade_tick_size\":"+DoubleToString(tick_size,8);
      result+=",\"trade_tick_value\":"+DoubleToString(SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_VALUE),8);
      result+=",\"volume_min\":"+DoubleToString(volume_min,8);
      result+=",\"volume_max\":"+DoubleToString(volume_max,8);
      result+=",\"volume_step\":"+DoubleToString(volume_step,8);
      result+=",\"swap_long\":"+DoubleToString(SymbolInfoDouble(symbol,SYMBOL_SWAP_LONG),8);
      result+=",\"swap_short\":"+DoubleToString(SymbolInfoDouble(symbol,SYMBOL_SWAP_SHORT),8);
      result+=",\"trade_mode\":"+IntegerToString((long)SymbolInfoInteger(symbol,SYMBOL_TRADE_MODE));
      result+=",\"candles\":"+candles+"}";
      accepted++;
     }
   result+="]";
   return(result);
  }

bool PublishMarketData()
  {
   string instruments=MetalInstrumentsJson();
   if(instruments=="[]")
     {
      Print("Matrades bridge: no broker metal symbols with live quotes and H1 candles were found.");
      return(false);
     }
   g_market_data_sequence++;
   string body="{\"account_id\":\""+JsonEscape(InpMatradesAccountId)+"\"";
   body+=",\"sequence\":"+IntegerToString((long)g_market_data_sequence);
   body+=",\"observed_at\":\""+IsoTime(TimeGMT())+"\"";
   body+=",\"broker\":\""+JsonEscape(AccountInfoString(ACCOUNT_COMPANY))+"\"";
   body+=",\"server\":\""+JsonEscape(AccountInfoString(ACCOUNT_SERVER))+"\"";
   body+=",\"timeframe\":\"H1\",\"instruments\":"+instruments+"}";
   string timestamp=IntegerToString((long)TimeGMT());
   string nonce=NewNonce();
   string signature=HmacSha256(timestamp+"."+nonce+"."+body,InpBridgeSecret);
   string headers="Content-Type: application/json\r\nX-Timestamp: "+timestamp+
                  "\r\nX-Nonce: "+nonce+"\r\nX-Signature: "+signature+"\r\n";
   uchar request_bytes[];
   char request_data[];
   char response_data[];
   StringBytes(body,request_bytes);
   ArrayResize(request_data,ArraySize(request_bytes));
   for(int index=0;index<ArraySize(request_bytes);index++)
      request_data[index]=(char)request_bytes[index];
   string response_headers="";
   int status=WebRequest("POST",BaseUrl()+"/market-data/ingest",headers,
                         InpRequestTimeoutMs,request_data,response_data,response_headers);
   if(status!=200)
     {
      PrintFormat("Matrades bridge market data publish failed: HTTP %d, error %d",status,GetLastError());
      return(false);
     }
   g_last_market_data_publish=TimeGMT();
   return(true);
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
      int error=GetLastError();
      if(status!=g_last_publish_status || error!=g_last_publish_error)
        {
         if(status==-1 && error==4014)
            Print("Matrades bridge WebRequest is disabled (error 4014). Enable Algorithmic Trading, allow this EA to trade, and add InpBridgeUrl under Tools > Options > Expert Advisors > Allow WebRequest.");
         else
            PrintFormat("Matrades bridge publish failed: HTTP %d, error %d",status,error);
        }
      g_last_publish_status=status;
      g_last_publish_error=error;
      return(false);
     }
   if(g_last_publish_status!=200)
      Print("Matrades bridge snapshot publishing recovered.");
   g_last_publish_status=200;
   g_last_publish_error=0;
   return(true);
  }

string JsonString(string body,string key)
  {
   string marker="\""+key+"\":\"";
   int start=StringFind(body,marker);
   if(start<0)
      return("");
   start+=StringLen(marker);
   int end=StringFind(body,"\"",start);
   return(end<0 ? "" : StringSubstr(body,start,end-start));
  }

double JsonNumber(string body,string key)
  {
   string marker="\""+key+"\":";
   int start=StringFind(body,marker);
   if(start<0)
      return(0.0);
   start+=StringLen(marker);
   int end=start;
   while(end<StringLen(body))
     {
      string character=StringSubstr(body,end,1);
      if(character=="," || character=="}" || character=="]")
         break;
      end++;
     }
   return(StringToDouble(StringSubstr(body,start,end-start)));
  }

bool WasProcessed(string command_id)
  {
   string global_name="MatradesCmd_"+command_id;
   if(GlobalVariableCheck(global_name))
      return(true);
   for(int index=0;index<ArraySize(g_processed_command_ids);index++)
      if(g_processed_command_ids[index]==command_id)
         return(true);
   return(false);
  }

void RememberProcessed(string command_id)
  {
   if(StringLen(command_id)==0 || WasProcessed(command_id))
      return;
   int size=ArraySize(g_processed_command_ids);
   ArrayResize(g_processed_command_ids,size+1);
   g_processed_command_ids[size]=command_id;
   GlobalVariableSet("MatradesCmd_"+command_id,(double)TimeCurrent());
  }

bool PostReceipt(string command_id,string idempotency_key,string state,string certainty,string broker_order_id,string error_code)
  {
   string body="{\"command_id\":\""+JsonEscape(command_id)+"\",\"account_id\":\""+
               JsonEscape(InpMatradesAccountId)+"\",\"idempotency_key\":\""+
               JsonEscape(idempotency_key)+"\",\"state\":\""+JsonEscape(state)+
               "\",\"outcome_certainty\":\""+JsonEscape(certainty)+"\",\"broker_order_id\":\""+
               JsonEscape(broker_order_id)+"\",\"error_code\":\""+JsonEscape(error_code)+"\"}";
   string timestamp=IntegerToString((long)TimeGMT());
   string nonce=NewNonce();
   string signature=HmacSha256(timestamp+"."+nonce+"."+body,InpBridgeSecret);
   string headers="Content-Type: application/json\r\nX-Timestamp: "+timestamp+
                  "\r\nX-Nonce: "+nonce+"\r\nX-Signature: "+signature+"\r\n";
   uchar request_bytes[];
   char request_data[];
   char response_data[];
   StringBytes(body,request_bytes);
   ArrayResize(request_data,ArraySize(request_bytes));
   for(int index=0;index<ArraySize(request_bytes);index++)
      request_data[index]=(char)request_bytes[index];
   string response_headers="";
   int status=WebRequest("POST",BaseUrl()+"/commands/receipts",headers,InpRequestTimeoutMs,
                         request_data,response_data,response_headers);
   return(status>=200 && status<300);
  }

bool ExecutePlaceOrder(string command,string &broker_order_id,string &error_code)
  {
   string symbol=JsonString(command,"instrument");
   double volume=JsonNumber(command,"quantity");
   if(StringLen(symbol)==0 || volume<=0.0)
     {
      error_code="invalid_order_payload";
      return(false);
     }
   if(!SymbolSelect(symbol,true))
     {
      error_code="symbol_unavailable";
      return(false);
     }
   MqlTradeRequest request={};
   MqlTradeResult result={};
   request.action=TRADE_ACTION_DEAL;
   request.symbol=symbol;
   request.volume=volume;
   request.type=JsonString(command,"direction")=="SELL" ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   request.price=request.type==ORDER_TYPE_SELL ? SymbolInfoDouble(symbol,SYMBOL_BID) : SymbolInfoDouble(symbol,SYMBOL_ASK);
   request.sl=JsonNumber(command,"stop_loss");
   request.tp=JsonNumber(command,"take_profit");
   request.deviation=20;
   request.type_filling=ORDER_FILLING_FOK;
   if(!OrderSend(request,result) || (result.retcode!=TRADE_RETCODE_DONE && result.retcode!=TRADE_RETCODE_PLACED))
     {
      error_code=IntegerToString((long)(result.retcode>0 ? result.retcode : GetLastError()));
      return(false);
     }
   broker_order_id=IntegerToString((long)result.order);
   return(true);
  }

bool SelectCommandPosition(string command,string symbol,ulong &ticket)
  {
   long supplied=(long)JsonNumber(command,"position_id");
   if(supplied>0 && PositionSelectByTicket((ulong)supplied))
     {
      ticket=(ulong)supplied;
      return(true);
     }
   if(StringLen(symbol)>0 && PositionSelect(symbol))
     {
      ticket=(ulong)PositionGetInteger(POSITION_TICKET);
      return(true);
     }
   return(false);
  }

bool ExecuteClose(string command,string &broker_order_id,string &error_code)
  {
   string symbol=JsonString(command,"instrument");
   ulong ticket=0;
   if(!SelectCommandPosition(command,symbol,ticket))
     {
      error_code="position_unavailable";
      return(false);
     }
   double current_volume=PositionGetDouble(POSITION_VOLUME);
   double volume=JsonNumber(command,"quantity");
   if(volume<=0.0 || volume>current_volume)
      volume=current_volume;
   long position_type=PositionGetInteger(POSITION_TYPE);
   MqlTradeRequest request={};
   MqlTradeResult result={};
   request.action=TRADE_ACTION_DEAL;
   request.position=ticket;
   request.symbol=PositionGetString(POSITION_SYMBOL);
   request.volume=volume;
   request.type=position_type==POSITION_TYPE_BUY ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   request.price=request.type==ORDER_TYPE_SELL ? SymbolInfoDouble(request.symbol,SYMBOL_BID) : SymbolInfoDouble(request.symbol,SYMBOL_ASK);
   request.deviation=20;
   request.type_filling=ORDER_FILLING_FOK;
   if(!OrderSend(request,result) || (result.retcode!=TRADE_RETCODE_DONE && result.retcode!=TRADE_RETCODE_PLACED))
     {
      error_code=IntegerToString((long)(result.retcode>0 ? result.retcode : GetLastError()));
      return(false);
     }
   broker_order_id=IntegerToString((long)result.order);
   return(true);
  }

bool ExecuteProtection(string command,string &broker_order_id,string &error_code)
  {
   string symbol=JsonString(command,"instrument");
   ulong ticket=0;
   if(!SelectCommandPosition(command,symbol,ticket))
     {
      error_code="position_unavailable";
      return(false);
     }
   MqlTradeRequest request={};
   MqlTradeResult result={};
   request.action=TRADE_ACTION_SLTP;
   request.position=ticket;
   request.symbol=PositionGetString(POSITION_SYMBOL);
   request.sl=JsonNumber(command,"stop_loss");
   request.tp=JsonNumber(command,"take_profit");
   if(!OrderSend(request,result) || result.retcode!=TRADE_RETCODE_DONE)
     {
      error_code=IntegerToString((long)(result.retcode>0 ? result.retcode : GetLastError()));
      return(false);
     }
   broker_order_id=IntegerToString((long)result.order);
   return(true);
  }

bool ExecuteCancel(string command,string &broker_order_id,string &error_code)
  {
   ulong order=(ulong)JsonNumber(command,"order_id");
   if(order==0)
     {
      error_code="order_id_required";
      return(false);
     }
   MqlTradeRequest request={};
   MqlTradeResult result={};
   request.action=TRADE_ACTION_REMOVE;
   request.order=order;
   if(!OrderSend(request,result) || result.retcode!=TRADE_RETCODE_DONE)
     {
      error_code=IntegerToString((long)(result.retcode>0 ? result.retcode : GetLastError()));
      return(false);
     }
   broker_order_id=IntegerToString((long)order);
   return(true);
  }

void PollCommands()
  {
   string timestamp=IntegerToString((long)TimeGMT());
   string nonce=NewNonce();
   string signature=HmacSha256(timestamp+"."+nonce+".",InpBridgeSecret);
   string headers="X-Timestamp: "+timestamp+"\r\nX-Nonce: "+nonce+"\r\nX-Signature: "+signature+"\r\n";
   char empty_request[];
   char response_data[];
   string response_headers="";
   string url=BaseUrl()+"/commands/poll?account_id="+InpMatradesAccountId+"&limit=10";
   int status=WebRequest("GET",url,headers,InpRequestTimeoutMs,empty_request,response_data,response_headers);
   if(status!=200)
      return;
   string response=CharArrayToString(response_data);
   int cursor=0;
   while((cursor=StringFind(response,"\"command_id\":\"",cursor))>=0)
     {
      int object_end=StringFind(response,"}",cursor);
      if(object_end<0)
         break;
      string command=StringSubstr(response,cursor,object_end-cursor+1);
      string command_id=JsonString(command,"command_id");
      string key=JsonString(command,"idempotency_key");
      string action=JsonString(command,"action");
      string order_id="";
      string error_code="";
      bool success=false;
      if(JsonString(command,"account_id")!=InpMatradesAccountId ||
         StringLen(JsonString(command,"authorization_digest"))==0)
        {
         PostReceipt(command_id,key,"REJECTED","NONE","","invalid_safety_scope");
         RememberProcessed(command_id);
         cursor=object_end+1;
         continue;
        }
      if(WasProcessed(command_id))
        {
         PostReceipt(command_id,key,"OUTCOME_UNKNOWN","UNCERTAIN","","duplicate_after_restart");
         cursor=object_end+1;
         continue;
        }
      if(action=="PLACE_ORDER")
         success=ExecutePlaceOrder(command,order_id,error_code);
      else if(action=="PARTIAL_CLOSE" || action=="FULL_EXIT")
         success=ExecuteClose(command,order_id,error_code);
      else if(action=="SET_OR_CHANGE_STOP_LOSS" || action=="SET_OR_CHANGE_TAKE_PROFIT")
         success=ExecuteProtection(command,order_id,error_code);
      else if(action=="CANCEL_ORDER")
         success=ExecuteCancel(command,order_id,error_code);
      else
         error_code="unsupported_action";
      RememberProcessed(command_id);
      PostReceipt(command_id,key,success ? "ACKNOWLEDGED" : "REJECTED",
                  success ? "CONFIRMED" : "NONE",order_id,error_code);
      cursor=object_end+1;
     }
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
   if(InpMarketDataPublishSeconds<5 || InpResearchCandleCount<3 ||
      InpResearchCandleCount>500 || InpMaxResearchMetalSymbols<1)
      return(INIT_PARAMETERS_INCORRECT);
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED))
      Print("Matrades bridge warning: Algorithmic Trading is disabled for the terminal or this EA; WebRequest and authorized command execution will remain unavailable.");
   MathSrand((int)GetTickCount());
   EventSetTimer(InpPublishSeconds);
   PublishSnapshot();
   PublishMarketData();
   PollCommands();
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
   if(TimeGMT()-g_last_market_data_publish>=InpMarketDataPublishSeconds)
      PublishMarketData();
   PollCommands();
  }

void OnTick()
  {
  }
//+------------------------------------------------------------------+
