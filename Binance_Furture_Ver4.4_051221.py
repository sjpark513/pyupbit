import ccxt
import pprint
import time
import datetime
import pandas as pd
import math

#########################################################################
# Binance_Furture_ver2_271121 
# 15분봉 이동평균 & MACD 이용
#########################################################################
Version = "Ver4.3 - 현재 사용 버전: 04.12.2021"

# 파이썬 판다스 모듈
pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
# 데이터프레임 내부의 정보가 다 보이도록 옵션 설정

#########################################################################
# 텔레그램 연결
#########################################################################
import telegram
tlgm_token = '1852462887:AAFbxcadwK1-Y89KdDcomBelHBpeBlBk7jM'
tlgm_id = '1505360897'
bot = telegram.Bot(token = tlgm_token)
updates = bot.getUpdates()

#########################################################################
# 바이낸스 연결
#########################################################################
api_key = "rMfSTki80SNOmtVingONGsAbBH81YUt6kxHAz8Drq20xhRNoDjI2tGRBDg927Ti4"
secret  = "1aFgD6hbv07Am6BPMVthPavajnsOqIG3J99O3fhvIysDCQxNxMdtUYyeFs8yQP3A"

binance = ccxt.binance(config={
    'apiKey': api_key, 
    'secret': secret,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future'
    }
})

#########################################################################
# 초기 변수
#########################################################################
Checkcnt = 0
RepeatCheckCnt = 2 # 10sec
StableCnt1 = 0
StableCnt2 = 0
StableCnt3 = 0
StableCnt4 = 0


#tickers = ['BTC/USDT','BCH/USDT','ETH/USDT','ETC/USDT','LTC/USDT']
tickers = ['BTC/USDT']
symbol = "BTC/USDT"

Setprice = 0
amount = 1.0

half_mode = True

op_mode = False 
position = {
    "type": None,
    "amount": 0
} 

markets = binance.load_markets()

market = binance.market(symbol)
leverage = 20

resp = binance.fapiPrivate_post_leverage({
    'symbol': market['id'],
    'leverage': leverage,
})

balance = binance.fetch_balance(params={"type": "future"})
usdt = balance['free']['USDT']
print(balance['USDT'])
           

#########################################################################
# 별도 데이터프레임 관리
#########################################################################
operation_df = pd.DataFrame(columns = ['ticker', 'resist_line'])

operation_df['ticker'] = tickers
operation_df.fillna(0, inplace=True) 

#########################################################################
# Functions
#########################################################################
def cal_amount(usdt_balance, cur_price, Order_rate):
    portion = Order_rate 
    usdt_trade = usdt_balance * portion * leverage
    amount = math.floor((usdt_trade * 100)/cur_price) / 100
    return amount 


def enter_position(exchange, symbol, cur_price, target_price, amount, position):
    if cur_price > target_price:         # 현재가 > long 목표가
        position['type'] = 'long'
        position['amount'] = amount
        exchange.create_market_buy_order(symbol=symbol, amount=amount)
    elif cur_price < target_price:      # 현재가 < short 목표가
        position['type'] = 'short'
        position['amount'] = amount
        exchange.create_market_sell_order(symbol=symbol, amount=amount)


def exit_position(exchange, symbol, position):
    amount = position['amount']
    if position['type'] == 'long':
        exchange.create_market_sell_order(symbol=symbol, amount=amount)
        position['type'] = None 
    elif position['type'] == 'short':
        exchange.create_market_buy_order(symbol=symbol, amount=amount)
        position['type'] = None 



'''
#########################################################################
# Initialize
#########################################################################
balance = binance.fetch_balance()
positions = balance['info']['positions']

for Bi_position in positions:    
    if Bi_position["symbol"] == "BTCUSDT" :
        if Bi_position["entryPrice"] > str(0.0) :
            op_mode = True
            if Bi_position["positionAmt"] > str(0.0) :            
                position['type'] = 'long'
                position['amount'] = Bi_position["positionAmt"]
            else :
                position['type'] = 'short'
                position['amount'] = Bi_position["positionAmt"] * -1              
'''

bot.sendMessage(chat_id = tlgm_id, text = 
            '\n바이낸스 선물 :' +Version+
            '\n코인: '+str(tickers)+
            '\nFreeUSDT :' +str(usdt))



while True: 
    for ticker in tickers :

        #now = datetime.datetime.now()
        
        ######################################################################
        # 차트데이터 가져오기
        ######################################################################
        ticker_df = binance.fetch_ohlcv(ticker, timeframe = '15m', limit = 100)
        ticker_df = pd.DataFrame(ticker_df, columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
        ticker_df['datetime'] = pd.to_datetime(ticker_df['datetime'], unit='ms')
        ticker_df.set_index('datetime', inplace=True)
        open_price  = ticker_df[  'open']
        high_price  = ticker_df[  'high']
        low_price   = ticker_df[   'low']
        close_price = ticker_df[ 'close']
        volume      = ticker_df['volume']
        cur_price = ticker_df['close'][-1]                     
        
        resist_line    = float(operation_df.loc[(operation_df.ticker == ticker),     'resist_line'])      


        ######################################################################
        # 이동평균 구하기
        ###################################################################### 
        ma5   = ticker_df[ 'ma5']  =  close_price.rolling(5).mean()
        ma10  = ticker_df[ 'ma10'] =  close_price.rolling(10).mean()   
        ma15  = ticker_df[ 'ma15'] =  close_price.rolling(15).mean()
        ma20  = ticker_df[ 'ma20'] =  close_price.rolling(20).mean()    
        ma25  = ticker_df[ 'ma25'] =  close_price.rolling(25).mean()     
    

        ######################################################################
        # MACD 구하기
        ###################################################################### 
        ShortEMA  = ticker_df[ 'ShortEMA'] =  close_price.ewm(span=12, adjust=False).mean()
        LongEMA   = ticker_df[ 'LongEMA'] =  close_price.ewm(span=26, adjust=False).mean()
        MACD = ShortEMA-LongEMA 
        Signal = MACD.ewm(span=9, adjust=False).mean() 
        CurrDiff = MACD - Signal

                
        ######################################################################
        # 매도 - 1분봉 체크
        ######################################################################             
        if op_mode and position['type'] is not None :
            '''
            ######################################################################
            # 1분봉 차트데이터 가져오기
            ######################################################################
            ticker_df1 = binance.fetch_ohlcv(ticker, timeframe = '15m', limit = 100)
            ticker_df1 = pd.DataFrame(ticker_df1, columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
            ticker_df1['datetime'] = pd.to_datetime(ticker_df1['datetime'], unit='ms')
            ticker_df1.set_index('datetime', inplace=True)            
            close_price = ticker_df1[ 'close']           

            ma1_60   = ticker_df1[ 'ma1_60']  =  close_price.rolling(60).mean()
            '''

            if position['type'] == 'long':
                print(" Long 매도 진입")
                #손절                    
                #if cur_price < ma25[-1] :            
                if cur_price < low_price[-2] and ma5[-1] < ma5[-2] :
                    exit_position(binance, ticker, position)
                    op_mode = False  
                    half_mode = True           
                              
                    print("long Position 손절!")

                    balance = binance.fetch_balance()
                    usdt = balance['free']['USDT']
                    print("Free USDT : ", usdt)
                    bot.sendMessage(chat_id = tlgm_id, text = 
                            '\n코인: '+str(ticker)+
                            '\n매도가: ' + str(round(cur_price,2))+
                            '\n손절매도: '+str(usdt))  

                    StableCnt1 = 0
                    StableCnt2 = 0
                    StableCnt3 = 0
                    StableCnt4 = 0  
                    Setprice = 0

                
                #익절 : 1.2% 수익시 50% 매도
                if op_mode and Setprice*1.003 < cur_price :       
                    if half_mode : 
                        half_mode = False          
                        enter_position(binance, ticker, cur_price, high_price[-1], amount*0.5, position)
                        bot.sendMessage(chat_id = tlgm_id, text = 
                            '\n코인: '+str(ticker)+ 
                            '\n매도가: '+str(cur_price)+                            
                            '\n1% 수익 익절') 

                    if cur_price < Setprice : 
                        exit_position(binance, ticker, position)
                        op_mode = False 
                        half_mode = True            
                                
                        print("long Position 전량 매도!")

                        balance = binance.fetch_balance()
                        usdt = balance['free']['USDT']
                        print("Free USDT : ", usdt)
                        bot.sendMessage(chat_id = tlgm_id, text = 
                                '\n코인: '+str(ticker)+
                                '\n매도가: ' + str(round(cur_price,2))+
                                '\n전량매도: '+str(usdt))  

                        StableCnt1 = 0
                        StableCnt2 = 0
                        StableCnt3 = 0
                        StableCnt4 = 0  
                        Setprice = 0

                    
                    '''
                    # 1분봉 60일 이탈시 전량 매도
                    if cur_price < ma1_60[-1] :
                        # 1분봉 60일 이탈시 전량 매도
                        exit_position(binance, ticker, position)
                        op_mode = False             
                                
                        print("long Position 전량 매도!")

                        balance = binance.fetch_balance()
                        usdt = balance['free']['USDT']
                        print("Free USDT : ", usdt)
                        bot.sendMessage(chat_id = tlgm_id, text = 
                                '\n코인: '+str(ticker)+
                                '\n매도가: ' + str(round(cur_price,2))+
                                '\n손절매도: '+str(usdt))  

                        StableCnt1 = 0
                        StableCnt2 = 0
                        StableCnt3 = 0
                        StableCnt4 = 0  
                        Setprice = 0
                    '''
                
                                    
            
            if position['type'] == 'short':
                print(" short 매도 진입")
                #손절                                   
                #if cur_price > ma25[-1] :    
                if cur_price > high_price[-2] and ma5[-1] > ma5[-2] :        
                    exit_position(binance, ticker, position)
                    op_mode = False 
                    half_mode = True 
                              
                    print("short Position 손절!")

                    balance = binance.fetch_balance()
                    usdt = balance['free']['USDT']
                    print("Free USDT : ", usdt)
                    bot.sendMessage(chat_id = tlgm_id, text = 
                            '\n코인: '+str(ticker)+
                            '\n매도가: ' + str(round(cur_price,2))+
                            '\n손절매도: '+str(usdt))
                    
                    StableCnt1 = 0
                    StableCnt2 = 0
                    StableCnt3 = 0
                    StableCnt4 = 0
                    Setprice = 0
                
                #익절 : 1.2% 수익시 50% 매도
                #if volume[-1] > (volume[-2] * 2) and Setprice*0.99 > cur_price and cur_price > low_price[-1] :
                if op_mode and Setprice*0.997 > cur_price : 
                    if half_mode :     
                        half_mode = False               
                        enter_position(binance, ticker, cur_price, low_price[-1], amount*0.5, position)
                        bot.sendMessage(chat_id = tlgm_id, text = 
                            '\n코인: '+str(ticker)+  
                            '\n매도가: '+str(cur_price)+                             
                            '\n1% 수익 익절') 
                    
                    if cur_price > Setprice :
                        exit_position(binance, ticker, position)
                        op_mode = False 
                        half_mode = True 
                                
                        print("short Position 전량 매도!")

                        balance = binance.fetch_balance()
                        usdt = balance['free']['USDT']
                        print("Free USDT : ", usdt)
                        bot.sendMessage(chat_id = tlgm_id, text = 
                                '\n코인: '+str(ticker)+
                                '\n매도가: ' + str(round(cur_price,2))+
                                '\n전량매도: '+str(usdt))
                        
                        StableCnt1 = 0
                        StableCnt2 = 0
                        StableCnt3 = 0
                        StableCnt4 = 0
                        Setprice = 0


                    '''
                    # 1분봉 60일 이탈시 전량 매도
                    if cur_price > ma1_60[-1] :
                        exit_position(binance, ticker, position)
                        op_mode = False  
                                
                        print("short Position 전량 매도!")

                        balance = binance.fetch_balance()
                        usdt = balance['free']['USDT']
                        print("Free USDT : ", usdt)
                        bot.sendMessage(chat_id = tlgm_id, text = 
                                '\n코인: '+str(ticker)+
                                '\n매도가: ' + str(round(cur_price,2))+
                                '\n손절매도: '+str(usdt))
                        
                        StableCnt1 = 0
                        StableCnt2 = 0
                        StableCnt3 = 0
                        StableCnt4 = 0
                        Setprice = 0
                    '''
                     
                
                                   
                
           
        
        ######################################################################
        # 매수 - 
        ######################################################################        
        # 추세 변환 Long Position
        if ma10[-3] < ma20[-3] and ma5[-2] < ma10[-2] < ma20[-2] : #역배열 체크
            print("Long 추세변환 진입1!")
            if ma10[-2] < ma10[-3] and ma20[-2] < ma20[-3] : # 하강 기울기 체크
                print("Long 추세변환 진입2!")
                if ma5[-1] > ma5[-2] and cur_price > ma20[-1] and volume[-1] > (volume[-2] * 1.5) : # 추세 변환 체크 
                    print("Long 추세변환 진입3")                   
                    if StableCnt1 > RepeatCheckCnt : 
                        if op_mode == False and position['type'] is None:
                            op_mode = True
                            StableCnt = 0
                            setprice = cur_price

                            balance = binance.fetch_balance()
                            usdt = balance['free']['USDT']
                            print("Free USDT : ", usdt)                            

                            #amount = cal_amount(usdt, setprice, 1.0)

                            enter_position(binance, ticker, setprice, ma20[-1], amount, position)          
                            print("Long Position!")                            
                            
                            bot.sendMessage(chat_id = tlgm_id, text = 
                                    '\n코인: '+str(ticker)+      
                                    '\nLong Position '+                      
                                    '\nFree USDT: '+ str(usdt)+
                                    '\n진입가: ' + str(round(setprice,2)))
                            # 텔레그램 메세지에 필요한 정보들을 송출합니다. 
                    
                    else : StableCnt1 = StableCnt1 + 1
                else : StableCnt1 = 0
            else : StableCnt1 = 0
        else : StableCnt1 = 0                         
        
        # 정배열 Long Position
        #if ma5[-1] > ma10[-1] > ma20[-1] : #정배열 체크
        if ma10[-1] > ma20[-1] and ma10[-2] > ma20[-2] : #정배열 체크
            print("Long 정배열 진입1!")
            if ma10[-1] > ma10[-2] and ma20[-1] > ma20[-2] : # 상승 기울기 체크 
                print("Long 정배열 진입2!")
                if volume[-1] > volume[-2] and cur_price > ma20[-1] : # 거래량 변환 체크
                    print("Long 정배열 진입3!")
                    if StableCnt2 > RepeatCheckCnt : 
                        if op_mode == False and position['type'] is None:
                            op_mode = True
                            StableCnt = 0
                            Setprice = cur_price
                            balance = binance.fetch_balance()
                            usdt = balance['free']['USDT']
                            print("Free USDT : ", usdt)

                            enter_position(binance, ticker, Setprice, ma20[-1], amount, position)          
                            print("Long Position!")                            
                            
                            bot.sendMessage(chat_id = tlgm_id, text = 
                                    '\n코인: '+str(ticker)+      
                                    '\nLong Position '+                      
                                    '\nFree USDT: '+ str(usdt)+
                                    '\n진입가: ' + str(round(Setprice,2)))
                            # 텔레그램 메세지에 필요한 정보들을 송출합니다. 
                    
                    else : StableCnt2 = StableCnt2 + 1
                else : StableCnt2 = 0
            else : StableCnt2 = 0 
        else : StableCnt2 = 0 




                    
        
        # 추세 변환 Short Position
        if ma10[-3] > ma20[-3] and ma5[-2] > ma10[-2] > ma20[-2] : #정배열 체크
            print("Short 추세변환 진입1!")
            if ma10[-2] > ma10[-3] and ma20[-2] > ma20[-3] : # 상승 기울기 체크
                print("Short 추세변환 진입2!")
                if ma5[-1] < ma5[-2] and cur_price < ma20[-1] and volume[-1] > (volume[-2] * 1.5) : # 추세 변환 체크     
                    print("Short 추세변환 진입3!")               
                    if StableCnt3 > RepeatCheckCnt : 
                        if op_mode == False and position['type'] is None:
                            op_mode = True
                            StableCnt = 0
                            Setprice = cur_price
                            balance = binance.fetch_balance()
                            usdt = balance['free']['USDT']
                            print("Free USDT : ", usdt)

                            enter_position(binance, ticker, Setprice, ma20[-1], amount, position)          
                            print("Short Position!")
                            
                            
                            bot.sendMessage(chat_id = tlgm_id, text = 
                                    '\n코인: '+str(ticker)+      
                                    '\nShort Position '+                      
                                    '\nFree USDT: '+ str(usdt)+
                                    '\n진입가: ' + str(round(Setprice,2)))
                            # 텔레그램 메세지에 필요한 정보들을 송출합니다. 
                    
                    else : StableCnt3 = StableCnt3 + 1
                else : StableCnt3 = 0
            else : StableCnt3 = 0
        else : StableCnt3 = 0                         
        
        # 역배열 Short Position
        if ma10[-1] < ma20[-1] and ma10[-2] < ma20[-2]: #역배열 체크
            print("Short 정배열 진입1!")
            if ma10[-1] < ma10[-2] and ma20[-1] < ma20[-2] : # 하강 기울기 체크 
                print("Short 정배열 진입2!")
                if volume[-1] > volume[-2] and cur_price < ma20[-1] : # 거래량 변환 체크
                    print("Short 정배열 진입3!")
                    if StableCnt4 > RepeatCheckCnt : 
                        if op_mode == False and position['type'] is None:
                            op_mode = True
                            StableCnt = 0
                            Setprice = cur_price
                            balance = binance.fetch_balance()
                            usdt = balance['free']['USDT']
                            print("Free USDT : ", usdt)

                            enter_position(binance, ticker, Setprice, ma20[-1], amount, position)          
                            print("Short Position!")                            
                            
                            bot.sendMessage(chat_id = tlgm_id, text = 
                                    '\n코인: '+str(ticker)+      
                                    '\nShort Position '+                      
                                    '\nFree USDT: '+ str(usdt)+
                                    '\n진입가: ' + str(round(Setprice,2)))
                            # 텔레그램 메세지에 필요한 정보들을 송출합니다. 
                    
                    else : StableCnt4 = StableCnt4 + 1
                else : StableCnt4 = 0
            else : StableCnt4 = 0 
        else : StableCnt4 = 0 


        
        ######################################################################
        # 정규 출력
        ######################################################################
        print(time.strftime('%H:%M:%S'),"       ", ticker)
        print("current_price  :", cur_price)
        print("StableCnt1  :", round(StableCnt1))
        print("StableCnt2  :", round(StableCnt2))
        print("StableCnt3  :", round(StableCnt3))
        print("StableCnt4  :", round(StableCnt4))  
        
        '''
        
        
        print("--------------------------------------")
        print("MACD        :", round(MACD[-1],2))        
        print("Signal      :", round(Signal[-1],2))        
        print("CurrDiff    :", round(CurrDiff[-1],2))  
        print("volume      :", round(volume[-1],2))
                     
        print("--------------------------------------")
        print("MACD[-2]        :", round(MACD[-2],2))        
        print("Signal[-2]      :", round(Signal[-2],2))        
        print("CurrDiff[-2]    :", round(CurrDiff[-2],2))
        print("volume[-2]          :", round(volume[-2],2))
        ''' 
        print("=======================================")

        Checkcnt = Checkcnt + 1
        if Checkcnt == 300 :
            Checkcnt = 0
            balance = binance.fetch_balance()
            usdt = balance['free']['USDT']
            bot.sendMessage(chat_id = tlgm_id, text = 
                '\n텔레그램 와치독!'+
                '\n코인: '+str(ticker)+
                '\nSet Price: '+str(Setprice)+ 
                '\ncur Price: '+str(cur_price)+   
                '\nFree USDT: '+ str(usdt))             

        time.sleep(2)
