import json
import threading
import time
from concurrent.futures import as_completed
from pynput import keyboard
from requests_futures.sessions import FuturesSession

from config import kc_client
from kucoin.client import Client

from pynput.keyboard import Listener, KeyCode

from rsrcs.useful_funcs import extract_coin_name


def keyboard_sell(coin_name, coin_amount, pairing_type):
    """This function sells with keyboard presses -  USED FOR PUMPS!
    press 'pg up' to sell on market
    press 'pg down' to sell on limit (which will be the highest buy ask for the coin)
    usually the optimal time to sell is twenty seconds after a pump, or around one minute after new listing """

    def sell_keypress(*key):
        try:
            if key[0] == keyboard.Key.page_up:
                print('\nlimit sell!')
                cur_price = kc_client.get_order_book(coin_name + f'-{pairing_type}')['asks'][0][0]
                order = kc_client.create_limit_order(coin_name + f'-{pairing_type}', Client.SIDE_SELL, price=cur_price,
                                                     size=coin_amount)
                print(f"limit sell order {order} happened!")

            elif key[0] == keyboard.Key.page_down:
                print('\nmarket sell!')
                order = kc_client.create_market_order(coin_name + f'-{pairing_type}', Client.SIDE_SELL,
                                                      size=coin_amount)
                print(f"market sell order {order} happened!")

        except Exception as err:
            print("ORDER SELL FAILED")
            print(f"{err.__class__} -- {err}")

    def key():  ## starts listener module
        with Listener(on_press=sell_keypress) as listener:
            listener.join()

    threading.Thread(target=key).start()


def buy_on_time(coin_name, USDT, offset, desired_time_utc):
    """ This function buys new listing on specified time - USED FOR NEW LISTINGS

        "USDT" is the amount of USDT to buy of the token. make sure you have enough USDT in balance
        "offset" is the upper bound percentage difference to place limit on
        "desired_time_utc"  is the time of the new listing, having on offset of 1 second late might be better.

         IE: fiat price is 100 and offset is 5%,  then order will be placed on 105, be careful when setting offset """
    my_timer = threading.Timer(1, buy_on_time, args=[coin_name, USDT, offset, desired_time_utc])
    my_timer.start()

    now_gmt = time.strftime("%H:%M:%S", time.gmtime())
    print(now_gmt)
    if now_gmt == desired_time_utc:
        print('\n time buying new listing!')
        __limit_buy_token(coin_name, USDT, offset)
        my_timer.cancel()
        # the order has happened on time, now stop this thread. we will enable


def keyboard_buy(coin_name, USDT, offset):
    """ This function is similar to buy_on_time, except that it buys with keyboard presses - USED FOR NEW LISTINGS
    press 'B' to create LIMIT ORDER on fiat price.
    press 'm' to buy market price! note: may not work due to new listing constraint. """

    def buy_keypress(*key):
        cur_order_id = 0
        if key[0] == KeyCode.from_char('b'):
            cur_order_id = __limit_buy_token(coin_name, USDT, offset)

        if key[0] == KeyCode.from_char('c'):
            kc_client.cancel_order(cur_order_id)

        if key[0] == KeyCode.from_char('m'):
            kc_client.create_market_order(coin_name + '-USDT', Client.SIDE_BUY, size=USDT)

    def key():  ## starts listener module
        with Listener(on_press=buy_keypress) as listener:
            listener.join()

    threading.Thread(target=key).start()


def extract_discord_coin_name(channel_id, headers):
    """This function is the main code used for discord scraping. it scraps the last message of the channel with id of
     {channel_id} each few milliseconds, and checks weather there is a coin name found for pumping or not,
     so essentially, as soon as pump message is sent out, we get the coin name - USED FOR PUMPS """
    session = FuturesSession()
    while True:

        future = session.get(f'https://discord.com/api/v9/channels/{channel_id}/messages?limit=1',
                             headers=headers)
        # print(future)

        try:
            last_msg = json.loads(future.result().text)[0]['content']
            c_name = extract_coin_name(last_msg, "USDT")
            print(last_msg)
            if c_name:  # if c_name isn't ''
                print(c_name)
                return c_name
        except Exception as err:
            print(f"{err.__class__} -- {err}")
            continue


def sell_on_target(coin_name, target_price, coin_amount, time_to_check, pairing_type):
    """
    USED FOR PUMPS (OPTIONALLY)

    this function places a limit order on the current price of the token being pumped as soon as it reaches the target

    coin name example: 'BTC'
    entry price is the price of the succeeded order
    sell_target_percentage is the target percentage we want to sell on as soon as we hit it. IE: 100% means we want 2x
    profit
    time_to_check is in second.  it will check for target each n seconds. a good default value is 0.8
    """

    my_timer = threading.Timer(time_to_check, sell_on_target,
                               args=[coin_name, target_price, coin_amount, time_to_check])
    my_timer.start()

    cur_price = kc_client.get_order_book(coin_name + f'-{pairing_type}')['asks'][0][0]
    if target_price < cur_price:
        order = kc_client.create_limit_order(coin_name + f'-{pairing_type}', Client.SIDE_SELL, price=target_price,
                                             size=coin_amount)
        print(f"{order} happened! selling on target price {str(target_price)}")
        my_timer.cancel()


def __limit_buy_token(coin_name, USDT, offset):
    """ sets a limit order based on the token name, USDT amount, and offset to the amount. - USED FOR NEW LISTINGS
    This functions is private, and used in the above functions.
     """
    cur_price = float(kc_client.get_fiat_prices(symbol=coin_name)[coin_name])  # get fiat or use asks
    cur_price += cur_price * (offset / 100)

    ord_bk_fa = kc_client.get_order_book(coin_name + '-USDT')['bids'][
        0]  # order book first order used to find decimal count
    num_decimals_price = ord_bk_fa[0][::-1].find('.')
    num_decimals_amount = ord_bk_fa[1][::-1].find('.')
    cur_price = float(f'%.{num_decimals_price}f' % cur_price)  # note cur_price always has to be float
    buy_amount = f'%.{num_decimals_amount}f' % (
            USDT / cur_price)
    order_id = kc_client.create_limit_order(coin_name + "-USDT", Client.SIDE_BUY, price=cur_price,
                                            size=buy_amount)
    print(f"limit buy order {order_id} happened!")
    return order_id
