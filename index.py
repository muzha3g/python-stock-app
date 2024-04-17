from flask import Flask, render_template, request, g, redirect
# g 是物件，可以儲存資訊
import sqlite3
import requests
import math
import matplotlib.pyplot as plt
import matplotlib
import os

matplotlib.use("agg")

app = Flask(__name__)
database = "datafile.db"


# 連接資料庫，g 有沒有後面參數的屬性，沒有的話就會去執行連接資料庫
def get_db():
    if not hasattr(g, "sqlite_db"):
        g.sqlite_db = sqlite3.connect(database)
    return g.sqlite_db


# 有連接就關閉連接，http request 結束後會執行
@app.teardown_appcontext
def close_connection(exception):
    print("正在關閉 sql 連接")
    if hasattr(g, "sqlite_db"):
        g.sqlite_db.close()


@app.route("/")
def home():
    conn = get_db()
    cursor = conn.cursor()
    result = cursor.execute("select * from cash")
    cash_result = result.fetchall()
    # 計算台幣與美金總額
    ntd = 0
    us = 0
    for data in cash_result:
        ntd += data[1]
        us += data[2]
    # 獲取匯率資訊，來源：全球及時匯率 api
    r = requests.get('https://tw.rter.info/capi.php')
    currency = r.json()
    total = math.floor(currency["USDTWD"]["Exrate"]*us + ntd)

    # 取得所有股票資訊
    result2 = cursor.execute("select * from stock")
    stock_result = result2.fetchall()
    unique_stock_list = []
    for data in stock_result:
        if data[1] not in unique_stock_list:
            unique_stock_list.append(data[1])
    # 計算股票總市值
    total_stock_value = 0

    # 計算單一股票資訊
    stock_info = []
    for stock in unique_stock_list:
        result = cursor.execute(
            "select * from stock where stock_id=?", (stock,))
        result = result.fetchall()
        stock_cost = 0  # 單一股票總花費
        shares = 0  # 單一股票股數
        for d in result:
            shares += d[2]
            stock_cost += d[2]*d[3]+d[4]+d[5]

        # 取得目前股價，證交所 api
        url = "https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&stockNo="+stock
        response = requests.get(url)
        data = response.json()
        price_array = data["data"]
        currency_price = float(price_array[len(price_array)-1][6])

        # 單一股票總市值
        total_value = int(currency_price*shares)
        total_stock_value += total_value

        # 單一股票平均成本
        average_cost = round(stock_cost/shares, 2)

        # 單一股票報酬率
        rate_of_return = round((total_value-stock_cost)*100/stock_cost, 2)

        stock_info.append({"stock_id": stock, "stock_cost": stock_cost,
                           "total_value": total_value, "average_cost": average_cost, "rate_of_return": rate_of_return, "shares": shares, "currency_price": currency_price})

    # 計算股票資產佔比
    for stock in stock_info:
        stock["value_percentage"] = round(
            stock["total_value"]*100/total_stock_value, 2)

    # 用 matplotlib 畫股票庫存占比圓餅圖
    if len(unique_stock_list) != 0:
        labels = tuple(unique_stock_list)
        sizes = [d["total_value"] for d in stock_info]
        fig, ax = plt.subplots(figsize=(6, 5))
        ax.pie(sizes, labels=labels, autopct=None, shadow=None)
        fig.subplots_adjust(top=1, bottom=0, right=1,
                            left=0, hspace=0, wspace=0)
        # 在根目錄建立一個 static 檔案夾
        plt.savefig("static/piechart.jpg", dpi=200)
    # 資料被刪掉的話，圖表也要被刪掉
    else:
        try:
            os.remove("static/piechart.jpg")
        except:
            pass

    # 用 matplotlib 畫股票現金圓餅圖
    if us != 0 or ntd != 0 or total_stock_value != 0:
        labels = tuple(["USD", "TWD", "Stock"])
        sizes = [us * currency["USDTWD"]["Exrate"], ntd, total_stock_value]
        fig, ax = plt.subplots(figsize=(6, 5))
        ax.pie(sizes, labels=labels, autopct=None, shadow=None)
        fig.subplots_adjust(top=1, bottom=0, right=1,
                            left=0, hspace=0, wspace=0)
        plt.savefig("static/piechart2.jpg", dpi=200)
    # 資料被刪掉的話，圖表也要被刪掉
    else:
        try:
            os.remove("static/piechart2.jpg")
        except:
            pass

    data = {"show_pic_1": os.path.exists("static/piechart.jpg"), "show_pic_2": os.path.exists("static/piechart2.jpg"), "total": total,
            "currency": currency["USDTWD"]["Exrate"], "us": us, "ntd": ntd, "cash_result": cash_result, "stock_info": stock_info}

    return render_template('index.html', data=data)


@app.route("/cash")
def cash():
    return render_template('cash.html')


@app.route("/cash", methods=["POST"])
def submit_cash():
    # 取得 cash 頁面，使育者提交的金額 + 資料
    ntd = 0
    us = 0
    if request.values["ntd"] != "":
        ntd = request.values["ntd"]
    if request.values["us"] != "":
        us = request.values["us"]
    note = request.values["note"]
    date = request.values["date"]

    # 更新數據庫資料
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """insert into cash (taiwanese_dollars,us_dollars,note,date_info) values (?,?,?,?)""", (ntd, us, note, date))
    conn.commit()

    # 將使用者導回首頁
    return redirect("/")


@app.route("/cash-delete", methods=["POST"])
def cash_delete():
    transaction_id = request.values["id"]
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """delete from cash where transaction_id=?""", (transaction_id))
    conn.commit()
    return redirect("/")


@app.route("/stock")
def stock():
    return render_template('stock.html')


@app.route("/stock", methods=["POST"])
def submit_stock():
    # 取得股票資訊、日期資訊
    stock_id = request.values["stock-id"]
    stock_num = request.values["stock-num"]
    stock_price = request.values["stock-price"]
    processing_fee = 0
    tax = 0
    if request.values["processing-fee"] != "":
        processing_fee = request.values["processing-fee"]
    if request.values["tax"] != "":
        tax = request.values["tax"]
    date = request.values["date"]

    # 更新數據庫資料
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """insert into stock (stock_id,stock_num,stock_price,processing_fee,tax,date_info) values (?,?,?,?,?,?)""", (stock_id, stock_num, stock_price, processing_fee, tax, date))
    conn.commit()

    return redirect("/")


if __name__ == '__main__':
    app.run(debug=True)
