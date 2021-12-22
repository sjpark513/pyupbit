import ccxt
import pprint
import time
import datetime
import pandas as pd
import math


#########################################################################
# Define
#########################################################################
amt = 0 #수량 정보 0이면 매수전(포지션 잡기 전), 양수면 롱 포지션 상태, 음수면 숏 포지션 상태
entryPrice = 0 #평균 매입 단가. 따라서 물을 타면 변경 된다.
leverage = 10   #레버리지, 앱이나 웹에서 설정된 값을 가져온다.
unrealizedProfit = 0 #미 실현 손익..그냥 참고용 

isolated = True #격리모드인지 

Debug_mode = False
Print_SW = False

#스탑로스 비율설정 0.5는 원금의 마이너스 50%를 의미한다. 0.1은 마이너스 10%
#맨 처음에는 적은 비중이 들어가므로 스탑로스를 0.9로 셋팅하는 것도 나쁘지 않으 듯 합니다.
stop_loass_rate = 0.8

#타겟 레이트 0.001 => 1%
target_rate = 0.005

Version = "New Version - Binance Furture 개선중 : Start 21.12.2021"
Sleep = 5

min_price = 0
max_price = 0
half_flag = True

preChk = 0

aa = 0
ab = 0
ac = 0
ad = 0
ba = 0
bb = 0
bc = 0
bd = 0
Checkcnt = 0
rsimin = 30
rsimax = 70

#거래할 코인 티커와 심볼
Target_Coin_Ticker = "BTC/USDT"
Target_Coin_Symbol = "BTCUSDT"



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
# 바이낸스 연결 - 06.12.2021 발급
#########################################################################
api_key = "xEYiwrNRUg3HeOjbrYQYqkLDsPSOG0sflvlUyzjBuWikGVLBPi1txd0nx2Dc6WND"
secret  = "HssqaBBgxzhXgDsp8VpSIhOcqoLWmkcf1r3MLno9vh0O9wQPnq1qJBAeWw81SBMI"


binance = ccxt.binance(config={
    'apiKey': api_key, 
    'secret': secret,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future'
    }
    
})

#########################################################################
# Bybit 연결 - 
#########################################################################
api_key = "j4S5p6DUM4DvKYjQ5l"
secret  = "ijs1RaQH3YXm9s0jUa9FceIrsA0l5NfmtvmQ"

bybit = ccxt.bybit(config={
    'apiKey': api_key, 
    'secret': secret,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future'
    }
})

#########################################################################
# Functions
#########################################################################
#RSI지표 수치를 구해준다. 첫번째: 분봉/일봉 정보, 두번째: 기간, 세번째: 기준 날짜
def GetRSI(ohlcv,period,st):
    ohlcv["close"] = ohlcv["close"]
    delta = ohlcv["close"].diff()
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0
    down[down > 0] = 0
    _gain = up.ewm(com=(period - 1), min_periods=period).mean()
    _loss = down.abs().ewm(com=(period - 1), min_periods=period).mean()
    RS = _gain / _loss
    return float(pd.Series(100 - (100 / (1 + RS)), name="RSI").iloc[st])

#이동평균선 수치를 구해준다 첫번째: 분봉/일봉 정보, 두번째: 기간, 세번째: 기준 날짜
def GetMA(ohlcv,period,st):
    close = ohlcv["close"]
    ma = close.rolling(period).mean()
    return float(ma[st])

#분봉/일봉 캔들 정보를 가져온다 첫번째: 바이낸스 객체, 두번째: 코인 티커, 세번째: 기간 (1d,4h,1h,15m,10m,1m ...)
def GetOhlcv(binance, Ticker, period):
    btc_ohlcv = binance.fetch_ohlcv(Ticker, period)
    df = pd.DataFrame(btc_ohlcv, columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
    df['datetime'] = pd.to_datetime(df['datetime'], unit='ms')
    df.set_index('datetime', inplace=True)
    return df


#스탑로스를 걸어놓는다. 해당 가격에 해당되면 바로 손절한다. 첫번째: 바이낸스 객체, 두번째: 코인 티커, 세번째: 손절 수익율 (1.0:마이너스100% 청산, 0.9:마이너스 90%, 0.5: 마이너스 50%)
def SetStopLoss(binance, Ticker, cut_rate):
    time.sleep(0.1)
    #주문 정보를 읽어온다.
    orders = binance.fetch_orders(Ticker)

    StopLossOk = False
    for order in orders:

        if order['status'] == "open" and order['type'] == 'stop_market':
            #print(order)
            StopLossOk = True
            break

    #스탑로스 주문이 없다면 주문을 건다!
    if StopLossOk == False:

        time.sleep(10.0)

        #잔고 데이타를 가지고 온다.
        balance = binance.fetch_balance(params={"type": "future"})
        time.sleep(0.1)
                                
        amt = 0
        entryPrice = 0
        leverage = 0
        #평균 매입단가와 수량을 가지고 온다.
        for posi in balance['info']['positions']:
            if posi['symbol'] == Ticker.replace("/", ""):
                entryPrice = float(posi['entryPrice'])
                amt = float(posi['positionAmt'])
                leverage = float(posi['leverage'])


        #롱일땐 숏을 잡아야 되고
        side = "sell"
        #숏일땐 롱을 잡아야 한다.
        if amt < 0:
            side = "buy"

        danger_rate = ((100.0 / leverage) * cut_rate) * 1.0

        #롱일 경우의 손절 가격을 정한다.
        stopPrice = entryPrice * (1.0 - danger_rate*0.01)

        #숏일 경우의 손절 가격을 정한다.
        if amt < 0:
            stopPrice = entryPrice * (1.0 + danger_rate*0.01)

        params = {
            'stopPrice': stopPrice,
            'closePosition' : True
        }
        
        #스탑 로스 주문을 걸어 놓는다.
        binance.create_order(Ticker,'STOP_MARKET',side,abs(amt),stopPrice,params)
        
        if Print_SW :
            print("side:",side,"   stopPrice:",stopPrice, "   entryPrice:",entryPrice)
            print("####STOPLOSS SETTING DONE ######################")

#구매할 수량을 구한다.  첫번째: 돈(USDT), 두번째:코인 가격, 세번째: 비율 1.0이면 100%, 0.5면 50%
def GetAmount(usd, coin_price, rate):

    target = usd * rate 

    amout = target/coin_price

    if amout < 0.001:
        amout = 0.001

    #print("amout", amout)
    return amout

#거래할 코인의 현재가를 가져온다. 첫번째: 바이낸스 객체, 두번째: 코인 티커
def GetCoinNowPrice(binance,Ticker):
    coin_info = binance.fetch_ticker(Ticker)
    coin_price = coin_info['last'] # coin_info['close'] == coin_info['last'] 

    return coin_price


        

#################################################################################################################
#영상엔 없지만 격리모드가 아니라면 격리모드로 처음 포지션 잡기 전에 셋팅해 줍니다,.
if isolated == False:
    try:
        binance.fapiPrivate_post_margintype({'symbol': Target_Coin_Symbol, 'marginType': 'ISOLATED'})
    except Exception as e:
        print("error:", e)
#################################################################################################################    
#################################################################################################################
#영상엔 없지만 레버리지를 3으로 셋팅합니다! 필요없다면 주석처리 하세요!
try:
    binance.fapiPrivate_post_leverage({'symbol': Target_Coin_Symbol, 'leverage': str(leverage)})
except Exception as e:
    print("error:", e)
#앱이나 웹에서 레버리지를 바뀌면 바뀌니깐 주의하세요!!
#################################################################################################################

min_price = GetCoinNowPrice(binance, Target_Coin_Ticker)
max_price = GetCoinNowPrice(binance, Target_Coin_Ticker)

balance = binance.fetch_balance(params={"type": "future"})
usdt = balance['free']['USDT']

bot.sendMessage(chat_id = tlgm_id, text = 
            '\n바이낸스 선물 :' +Version+
            '\n코인: '+str(Target_Coin_Ticker)+
            '\nFreeUSDT :' +str(usdt))


#########################################################################
# Main loop
#########################################################################

while True :
    try :
        #########################################################################
        # Update
        #########################################################################
        #캔들 정보 가져온다
        df_15 = GetOhlcv(binance,Target_Coin_Ticker, '15m')
        df_5  = GetOhlcv(binance,Target_Coin_Ticker, '5m')
        df_1  = GetOhlcv(binance,Target_Coin_Ticker, '1m')

        #잔고 데이타 가져오기 
        balance = binance.fetch_balance(params={"type": "future"})
        #time.sleep(0.1)

        #실제로 잔고 데이타의 포지션 정보 부분에서 해당 코인에 해당되는 정보를 넣어준다.
        for posi in balance['info']['positions']:
            if posi['symbol'] == Target_Coin_Symbol:
                amt = float(posi['positionAmt'])
                entryPrice = float(posi['entryPrice'])
                leverage = float(posi['leverage'])
                unrealizedProfit = float(posi['unrealizedProfit'])
                isolated = posi['isolated']
                break
        
        #해당 코인 가격을 가져온다.
        coin_price = GetCoinNowPrice(binance, Target_Coin_Ticker)

        #레버리지에 따른 최대 매수 가능 수량
        Max_Amount = round(GetAmount(float(balance['USDT']['total']),coin_price,0.5),3) * leverage 

        #최대 매수수량의 1%에 해당하는 수량을 구한다.
        one_percent_amount = Max_Amount / 50.0        

        #첫 매수 비중을 구한다.. 여기서는 50%!
        first_amount = one_percent_amount * 50.0

        if first_amount < 0.001:
            first_amount = 0.001

        #음수를 제거한 절대값 수량 ex -0.1 -> 0.1 로 바꿔준다.
        abs_amt = abs(amt)

        #타겟 수익율 0.1%
        target_revenue_rate = target_rate * 100.0

        
        ######################################################################
        # 이동 평균 구하기  
        ######################################################################
        # 5분봉 이동평균                
        ma5_5m_before2     = GetMA(df_5, 5, -3)
        ma5_5m_before1     = GetMA(df_5, 5, -2)
        ma5_5m             = GetMA(df_5, 5, -1)        
        ma20_5m_before2    = GetMA(df_5, 20, -3)
        ma20_5m_before1    = GetMA(df_5, 20, -2)
        ma20_5m            = GetMA(df_5, 20, -1)


        ######################################################################
        # RSI14 정보를 가지고 온다.  
        ######################################################################        
        rsi6_15m_before2 = GetRSI(df_15, 6, -3)
        rsi6_15m_before1 = GetRSI(df_15, 6, -2)
        rsi6_15m         = GetRSI(df_15, 6, -1)

        rsi6_5m_before2 = GetRSI(df_5, 6, -3)
        rsi6_5m_before1 = GetRSI(df_5, 6, -2)
        rsi6_5m         = GetRSI(df_5, 6, -1)
        
        
        ######################################################################
        # 볼린저 밴드 구하기  
        ######################################################################
        # 15분봉 BB
        ma20_15m_bb  = df_15['close'].rolling(20).mean()        
        std20_15m = df_15['close'].rolling(20).std()
        bu20_15m  = ma20_15m_bb + std20_15m * 2
        bd20_15m  = ma20_15m_bb - std20_15m * 2 

        perB_15m = (df_15['close'] - bd20_15m) / (bu20_15m - bd20_15m)
        
        # 5분봉 BB
        ma20_5m_bb  = df_5['close'].rolling(20).mean()        
        std20_5m = df_5['close'].rolling(20).std()
        bu20_5m  = ma20_5m_bb + std20_5m * 2
        bd20_5m  = ma20_5m_bb - std20_5m * 2 

        perB_5m = (df_5['close'] - bd20_5m) / (bu20_5m - bd20_5m)
        
        
        # 최저가 찾기
        if min_price > df_15['low'][-1] :
            min_price = df_15['low'][-1]
        

        # 최고가 찾기
        if max_price < df_15['high'][-1] :
            max_price = df_15['high'][-1]


        if Print_SW :            
            print("Bollinger 5m : ", round(perB_5m[-3],4)," ", round(perB_5m[-2],4), " ", round(perB_5m[-1],4))
            print("Bollinger 15m : ", round(perB_15m[-3],4)," ", round(perB_15m[-2],4), " ", round(perB_15m[-1],4))
            print("최저가 : ",min_price, "최고가 : ", max_price)

        
               
        


        ###############################################
        ##### 매우 중요!!! 조건 트리거
        ###############################################        

        ################################################################ Long Position ########################################################################################               
        # 5분봉 bb 
        if (perB_5m[-2] < 0.02 and perB_5m[-1] >= 0.02) :#or (bd20_5m[-2] > df_5['low'][-2] and bd20_5m[-1] < df_5['low'][-1]) :
            aa = 1
            ab = 1
            ac = 1
            ad = 1
            preChk = perB_5m[-2]
        else : 
            aa = 0          
            ab = 0
            ac = 0
            ad = 0
         
        
        
        
        
        ############################################################### Short Position #######################################################################################
        # 1분봉 역배열 찾기
        if (perB_5m[-2] > 0.98 and perB_5m[-1] <= 0.98) :#or (bd20_5m[-2] < df_5['high'][-2] and bd20_5m[-1] > df_5['high'][-1]) :                
            ba = 1
            bb = 1
            bc = 1
            bd = 1
            preChk = perB_5m[-2]
        else : 
            ba = 0           
            bb = 0
            bc = 0
            bd = 0




                
            
        if Print_SW :
            print("one_percent_amount : ", one_percent_amount)
            print("first_amount : ", first_amount)           
            print("Long Position 확인   : ", aa," ", ab, " ", ac, " ", ad)
            print("Short Posotion 확인  : ", ba," ", bb, " ", bc, " ", bd)
        
        
        #0이면 포지션 잡기전
        if amt == 0:
            #print("-----------------------------No Position---------------------------------")
            half_flag = True
          
            ### long 진입
            if aa and ab and ac and ad :                            
                #해당 코인 가격을 가져온다.
                coin_price = GetCoinNowPrice(binance, Target_Coin_Ticker)

                if Debug_mode :                    
                    print("buy/long 진입 진입 : ", coin_price)
                    

                else :
                    #주문 취소후
                    binance.cancel_all_orders(Target_Coin_Ticker)
                    #time.sleep(0.1)
                    
                    #숏 포지션을 잡는다
                    print(binance.create_limit_buy_order(Target_Coin_Ticker, first_amount, coin_price))

                    #스탑 로스 설정을 건다.
                    SetStopLoss(binance,Target_Coin_Ticker,stop_loass_rate) #미션 수행
                
                bot.sendMessage(chat_id = tlgm_id, text = 
                        '\n바이낸스 선물 :' +Version+
                        '\nbuy/long 진입 진입 : '+str(coin_price)+
                        '\ntime: '+str(time.strftime('%H:%M:%S')))       


            ### short 진입
            if ba and bb and bc and bd :
                
                #해당 코인 가격을 가져온다.
                coin_price = GetCoinNowPrice(binance, Target_Coin_Ticker)
                
                if Debug_mode :                    
                    print("sell/short 진입 : ", coin_price)
                    

                else :
                    #주문 취소후
                    binance.cancel_all_orders(Target_Coin_Ticker)
                    #time.sleep(0.1)                   

                    #롱 포지션을 잡는다
                    print(binance.create_limit_sell_order(Target_Coin_Ticker, first_amount, coin_price))

                    #스탑 로스 설정을 건다.
                    SetStopLoss(binance,Target_Coin_Ticker,stop_loass_rate) #미션 수행
                
                bot.sendMessage(chat_id = tlgm_id, text = 
                        '\n바이낸스 선물 :' +Version+
                        '\nsell/short 진입 : '+str(coin_price)+                        
                        '\ntime: '+str(time.strftime('%H:%M:%S')))     
            


    
        #0이 아니라면 포지션 잡은 상태 -
        else:
            #print("------------------------------------------------------")

            #현재까지 구매한 퍼센트! 현재 보유 수량을 1%의 수량으로 나누면 된다.
            buy_percent = abs_amt / one_percent_amount
            

            #수익율을 구한다!
            revenue_rate = (coin_price - entryPrice) / entryPrice * 100.0
            #단 숏 포지션일 경우 수익이 나면 마이너스로 표시 되고 손실이 나면 플러스가 표시 되므로 -1을 곱하여 바꿔준다.
            if amt < 0:
                revenue_rate = revenue_rate * -1.0

            #레버리지를 곱한 실제 수익율
            leverage_revenu_rate = revenue_rate * leverage
            

            #손절 마이너스 수익율을 셋팅한다.
            danger_rate = -5.0
            #레버리지를 곱한 실제 손절 할 마이너스 수익율
            leverage_danger_rate = danger_rate * leverage

            

            '''
            40  + 5
            70  + 10
            20   + 20
            40   + 40
            80  + 20
            '''

            #추격 매수 즉 물 탈 마이너스 수익율을 셋팅한다.
            water_rate = -1.0

            ###########미션응용??###############
            #보유 비중에 따라 스탑로스를 다르게 걸 수도 있겠죠?
            #적은 비중이라면 스탑로스를 멀게 (0.9, 90%) 많은 비중이라면 스탑로스를 가깝게 (0.1, 10%) 하는 것도 하나의 전략이 됩니다.
            if buy_percent <= 50.0:
                water_rate = -0.5 
                
            elif buy_percent <= 10.0:
                water_rate = -1.0 
                
            elif buy_percent <= 80.0:
                water_rate = -5.0 
                


            #레버리지를 곱한 실제 물 탈 마이너스 수익율
            leverage_danger_rate = water_rate * leverage


            if Print_SW :
                print("Buy Percent : ", buy_percent)
                print("Revenue Rate : ", revenue_rate,", Real Revenue Rate : ", leverage_revenu_rate, "target_revenue_rate : ", target_revenue_rate)
                print("Danger Rate : ", danger_rate,", Real Danger Rate : ", leverage_danger_rate)
                print("Water Rate : ", water_rate,", Real Water Rate : ", leverage_danger_rate)        




            #음수면 숏 포지션 상태
            if amt < 0:
               # print("-----Short Position")     
                if bb and preChk != perB_5m[-2]:
                     #물탈 수량 
                    water_amount = abs_amt

                    if Max_Amount < abs_amt + water_amount:
                        water_amount = Max_Amount - abs_amt

                        #주문 취소후
                        binance.cancel_all_orders(Target_Coin_Ticker)
                        time.sleep(0.1)
                        
                        #해당 코인 가격을 가져온다.
                        coin_price = GetCoinNowPrice(binance, Target_Coin_Ticker)

                        #숏 포지션을 잡는다
                        print(binance.create_limit_sell_order(Target_Coin_Ticker, water_amount, coin_price))

                        #스탑 로스 설정을 건다.
                        SetStopLoss(binance,Target_Coin_Ticker,stop_loass_rate) #미션 수행

                        bot.sendMessage(chat_id = tlgm_id, text = 
                        '\n바이낸스 선물 :' +Version+
                        '\nsell/short 재진입 : '+str(coin_price)+                        
                        '\ntime: '+str(time.strftime('%H:%M:%S'))) 

                #수익이 났다!!! 50% 익절!
                if revenue_rate >= target_revenue_rate :
                    
                    if half_flag :                       
                        
                        half_flag = False         
                        #print("수익이 났다!!! 50% 익절!")
                        #target_rate = target_rate + 0.005
                        #주문 취소후
                        binance.cancel_all_orders(Target_Coin_Ticker)
                        time.sleep(0.1)
                        
                        #해당 코인 가격을 가져온다.
                        coin_price = GetCoinNowPrice(binance, Target_Coin_Ticker)

                        #롱 포지션을 잡는다
                        binance.create_limit_buy_order(Target_Coin_Ticker, first_amount * 0.5, coin_price)

                        #스탑 로스 설정을 건다.
                        #SetStopLoss(binance,Target_Coin_Ticker,stop_loass_rate) #미션 수행"buy"
                        params = {
                            'stopPrice': coin_price,
                            'closePosition' : True
                        }

                        binance.create_order(Target_Coin_Ticker,'STOP_MARKET',"buy",abs(first_amount * 0.5),coin_price,params)

                        bot.sendMessage(chat_id = tlgm_id, text = 
                            '\n바이낸스 선물 :' +Version+
                            '\nsell/short 10% 익절 : '+str(coin_price)+
                            '\ntime: '+str(time.strftime('%H:%M:%S')))
                    else :
                        if aa :
                            #주문 취소후
                            binance.cancel_all_orders(Target_Coin_Ticker)
                            time.sleep(0.1)
                            
                            #해당 코인 가격을 가져온다.
                            coin_price = GetCoinNowPrice(binance, Target_Coin_Ticker)

                            #롱 포지션을 잡는다
                            print(binance.create_limit_buy_order(Target_Coin_Ticker, abs_amt + first_amount, coin_price))

                            #스탑 로스 설정을 건다.
                            SetStopLoss(binance,Target_Coin_Ticker,stop_loass_rate) #미션 수행

                            bot.sendMessage(chat_id = tlgm_id, text = 
                            '\n바이낸스 선물 :' +Version+
                            '\nsell/short 익절 매도 / 반대 매수 : '+str(coin_price)+
                            '\ntime: '+str(time.strftime('%H:%M:%S')))

                    

                else :          
                    # 손절 : 20일선 이탈시
                    if coin_price > max_price :
                    #if coin_price > ma20_15m :
                    #if ma5_5m > ma5_5m_before1 and ma5_5m_before2 > ma5_5m_before1 :
                        #주문 취소후
                        binance.cancel_all_orders(Target_Coin_Ticker)
                        time.sleep(0.1)
                            
                        #해당 코인 가격을 가져온다.
                        coin_price = GetCoinNowPrice(binance, Target_Coin_Ticker)

                        #롱 포지션을 잡는다
                        #binance.create_limit_buy_order(Target_Coin_Ticker, abs_amt, coin_price)

                        bot.sendMessage(chat_id = tlgm_id, text = 
                            '\n바이낸스 선물 :' +Version+
                            '\nsell/short 전량 매도 : '+str(coin_price)+
                            '\ntime: '+str(time.strftime('%H:%M:%S')))

                        #################################################################### 추세 변환으로 봐도 될까???? 고민해봐
                          

            
            #양수면 롱 포지션 상태
            else:
                #print("-----Long Position")                
                if aa and preChk != perB_5m[-2]:
                     #물탈 수량 
                    water_amount = abs_amt

                    if Max_Amount < abs_amt + water_amount:
                        water_amount = Max_Amount - abs_amt

                        #주문 취소후
                        binance.cancel_all_orders(Target_Coin_Ticker)
                        time.sleep(0.1)
                        
                        #해당 코인 가격을 가져온다.
                        coin_price = GetCoinNowPrice(binance, Target_Coin_Ticker)

                        #숏 포지션을 잡는다
                        print(binance.create_limit_buy_order(Target_Coin_Ticker, water_amount, coin_price))

                        #스탑 로스 설정을 건다.
                        SetStopLoss(binance,Target_Coin_Ticker,stop_loass_rate) #미션 수행

                        bot.sendMessage(chat_id = tlgm_id, text = 
                        '\n바이낸스 선물 :' +Version+
                        '\nbuy/long 재진입 : '+str(coin_price)+                        
                        '\ntime: '+str(time.strftime('%H:%M:%S')))

                #수익이 났다!!! 숏 포지션 종료하고 롱 포지션도 잡아주자!
                if revenue_rate >= target_revenue_rate :
                    
                    if half_flag:
                        
                        half_flag = False          
                        #print("수익이 났다!!! 50% 익절!")
                        #target_rate = target_rate + 0.005
                        #주문 취소후
                        binance.cancel_all_orders(Target_Coin_Ticker)
                        time.sleep(0.1)
                        
                        #해당 코인 가격을 가져온다.
                        coin_price = GetCoinNowPrice(binance, Target_Coin_Ticker)

                        #롱 포지션을 잡는다
                        binance.create_limit_sell_order(Target_Coin_Ticker, first_amount * 0.5, coin_price)

                        params = {
                            'stopPrice': coin_price,
                            'closePosition' : True
                        }

                        #스탑 로스 설정을 건다.
                        binance.create_order(Target_Coin_Ticker,'STOP_MARKET',"sell",abs(first_amount * 0.5),coin_price, params)

                        bot.sendMessage(chat_id = tlgm_id, text = 
                            '\n바이낸스 선물 :' +Version+
                            '\nbuy/long 10% 익절 : '+
                            '\coin_price :' +str(coin_price)+
                            '\ntime: '+str(time.strftime('%H:%M:%S')))
                    else :
                        if bb :
                            #주문 취소후
                            binance.cancel_all_orders(Target_Coin_Ticker)
                            time.sleep(0.1)
                            
                            #해당 코인 가격을 가져온다.
                            coin_price = GetCoinNowPrice(binance, Target_Coin_Ticker)

                            #롱 포지션을 잡는다
                            print(binance.create_limit_sell_order(Target_Coin_Ticker, abs_amt + first_amount, coin_price))

                            #스탑 로스 설정을 건다.
                            SetStopLoss(binance,Target_Coin_Ticker,stop_loass_rate) #미션 수행

                            bot.sendMessage(chat_id = tlgm_id, text = 
                            '\n바이낸스 선물 :' +Version+
                            '\nbuy/long 익절 매도 / 반대 매수 : '+str(coin_price)+
                            '\ntime: '+str(time.strftime('%H:%M:%S')))
                    
                
                else :
                    # 손절 : 20일선 이탈시
                    if coin_price < min_price :
                    #if coin_price < ma20_15m :
                    #if ma5_5m < ma5_5m_before1 and ma5_5m_before2 < ma5_5m_before1 :
                        #주문 취소후
                        binance.cancel_all_orders(Target_Coin_Ticker)
                        time.sleep(0.1)
                            
                        #해당 코인 가격을 가져온다.
                        coin_price = GetCoinNowPrice(binance, Target_Coin_Ticker)

                        #롱 포지션을 잡는다
                      #  binance.create_limit_sell_order(Target_Coin_Ticker, abs_amt, coin_price)

                        bot.sendMessage(chat_id = tlgm_id, text = 
                            '\n바이낸스 선물 :' +Version+
                            '\nbuy/long 전량 매도 : '+str(coin_price)+
                            '\ntime: '+str(time.strftime('%H:%M:%S'))) 
       

        
        ######################################################################
        # 정규 출력
        ###################################################################### 
        if Print_SW : 
            print("---------------------------------") 
            print(time.strftime('%H:%M:%S'),"       ", Target_Coin_Ticker)

            print("Free USDT : ", usdt) 
            print("cur_price : ", coin_price)
            #print("rsi14 : ", rsi14)
            
    
            print("=================================")        
        #지정가 주문만 있기 때문에 혹시나 스탑로스가 안걸릴 수 있어서 마지막에 한번 더 건다
        #해당 봇이 서버에서 주기적으로 실행되기 때문에 실행 될때마다 체크해서 걸어 줄 수 있다.
        #스탑 로스 설정을 건다.
        #SetStopLoss(binance,Target_Coin_Ticker,stop_loass_rate) #미션 수행

        Checkcnt = Checkcnt + 1
        if Checkcnt == 50 :
            Checkcnt = 0
            balance = binance.fetch_balance()
            usdt = balance['free']['USDT']           
            bot.sendMessage(chat_id = tlgm_id, text = 
                '\n텔레그램 와치독!'+
                '\n최저가: '+str(min_price)+ 
                '\n최고가: '+str(max_price)+
                '\nBollinger : '+str(round(perB_5m[-3]-0.004,4))+' '+str(round(perB_5m[-2]-0.004,4))+' '+str(round(perB_5m[-1],4))+
                '\ncur Price: '+str(coin_price)+   
                '\nFree USDT: '+ str(usdt))

        time.sleep(Sleep)

    except Exception as e:
        print(e)
        time.sleep(1)



#########################################################################
# Block 
#########################################################################
'''
balance = binance.fetch_balance()
        usdt = balance['free']['USDT']
            
        tickerbel = binance.fetch_ticker(symbol)
        cur_price = tickerbel['last']

#캔들 정보 가져온다
        df_15 = GetOhlcv(binance, Target_Coin_Ticker, '15m')      

        #RSI14 정보를 가지고 온다.
        rsi14 = GetRSI(df_15, 14, -1)
        print(rsi14)

        #해당 코인 가격을 가져온다.
        coin_price = GetCoinNowPrice(binance, Target_Coin_Ticker)

        #최근 3개의 종가 데이터
        print("Price: ",df_15['close'][-3], "->",df_15['close'][-2], "->",df_15['close'][-1] )
        #최근 3개의 5일선 데이터
        print("5ma: ",GetMA(df_15, 5, -3), "->",GetMA(df_15, 5, -2), "->",GetMA(df_15, 5, -1))
        #최근 3개의 RSI14 데이터
        print("RSI14: ",GetRSI(df_15, 14, -3), "->",GetRSI(df_15, 14, -2), "->",GetRSI(df_15, 14, -1))



'''