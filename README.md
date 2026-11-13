# My Long-Term Tracker

A page for your phone that updates itself every evening, with no laptop needed after setup.

- **Holdings**: you add what you bought (date, price, quantity). Each day it shows Sell, Review, Room to add or Hold with the reason, your profit or loss, and how many days remain until the gain is taxed at the long-term rate.
- **Ideas**: the stocks in your list that pass 6 price-trend checks. Optionally only those on your own Screener.in lists.
- **News**: what is happening in the market, India first then the world, the stocks in the news, and stocks to watch. Refreshed every weekday morning and evening.
- **Look up**: search any stock in your list.
- **Settings**: your rules (most per stock, stop %, trailing stop, and so on), plus backup and restore.

Everything is free. The prices are end-of-day Yahoo Finance data. Your holdings are stored **only in the browser on your phone**, never in GitHub.

> Education and tooling, not financial advice. The signals are simple price rules. They cannot see results, news or fraud, and nobody can tell you the right day to sell. Most of the work is deciding what you are willing to lose before you buy.

## One-time setup (about 20 minutes, on your laptop, at the weekend)

You need a free GitHub account and Git (you already have both).

1. **Unzip** this folder, for example to `D:\trading\longterm-tracker`.
2. **Copy your stock list in.** In PowerShell:
   ```
   cd D:\trading\longterm-tracker
   Copy-Item D:\trading\trader\universe.txt data\universe.txt
   ```
   (That is the 496-stock Nifty 500 list you downloaded earlier. Add ETFs or other symbols to `data\extra.txt`.)
3. **Optional: your own lists.** Open `data\screens.txt` and put your Screener.in stocks under `## LT Quality Compounders` and `## LT High Growth Watch`, one symbol a line (for example `JIOFIN`).
4. **Test it on your laptop first** (takes a minute):
   ```
   python scripts\update.py --limit 20
   python -m http.server 8000 --directory docs
   ```
   Open http://localhost:8000 in your browser. Press Ctrl+C in PowerShell to stop.
5. **Create the GitHub repository.** On github.com click New repository. Name it something like `my-tracker`, choose **Public** (GitHub's free Pages needs this; the repo holds only market data and rules, not your holdings), and do not add a README. Create it.
6. **Upload.** In PowerShell, in the project folder, replacing YOUR-NAME and the repo name:
   ```
   git init
   git add .
   git commit -m "first version"
   git branch -M main
   git remote add origin https://github.com/YOUR-NAME/my-tracker.git
   git push -u origin main
   ```
   A browser window may ask you to sign in to GitHub.
7. **Turn on the web page.** In the repository: Settings, Pages, Source = "Deploy from a branch", Branch = `main`, Folder = `/docs`, Save.
8. **Run the first update.** Open the **Actions** tab. If asked, click the button to enable workflows. Choose **Daily update**, then **Run workflow**. It takes about 5 to 10 minutes. A green tick means it worked.
9. **Open your page** at `https://YOUR-NAME.github.io/my-tracker/` (the Pages settings screen shows the exact link). On your phone, open it and use "Add to Home screen".

From then on GitHub refreshes the data every weekday: news at about 8:30 AM IST and everything again at about 6:00 PM IST. Pull down to reload the page on your phone.

## Using it

- Buy in your broker app as usual, then open the page, **Holdings**, **Add a stock I bought**, and enter the date, quantity and price. Do this on each device you use, or use Settings, Backup to move them.
- Check it in the evening. Sell and Review rows appear first.
- A Sell or Review signal is a prompt to look at the news and results, then decide. It is not an order.
- Different phones keep separate holdings. Use Backup and Restore in Settings to copy them across.

## If something goes wrong

- **Page says "No price data yet"**: the first update has not run. Actions, Daily update, Run workflow.
- **Banner says prices are N days old**: Actions, Daily update, Run workflow. GitHub can pause scheduled jobs on a repository with no activity for a long time, and Yahoo can rate-limit GitHub's servers. If a run fails, the old data stays in place and stocks that could not refresh are marked old.
- **A stock is missing**: it is not in `data\universe.txt` or `data\extra.txt`. Add it there on GitHub (edit the file in the browser) and run the update again.
- **Update keeps failing on GitHub**: run `python scripts\update.py` on your laptop, then `git add docs/market.json`, `git commit -m "manual data"`, `git push`.

## The News tab

Three views, refreshed by GitHub every weekday at about 8:30 AM IST (world markets and overnight news before the Indian open) and about 6:00 PM IST (after the NSE close, together with the price update):

- **India**: Nifty 50, Sensex, Bank Nifty and India VIX; the latest Indian headlines; your tracked Indian stocks that are named in the headlines; and the biggest gainers and losers on your list.
- **World**: S&P 500, Nasdaq, Dow, FTSE, DAX, Nikkei, Hang Seng, the dollar in rupees, Brent crude and gold; world headlines; large US stocks named in the headlines; and the biggest US movers.
- **To watch**: Indian stocks on unusually high trading volume with a big price move (the page says why each is listed), the newspapers' own "stocks to watch" articles, and the same for global stocks.

Where it comes from: the publishers' own RSS feeds listed in `data/feeds.txt` (only the headline, source, time and a link back are kept) and Yahoo Finance daily prices. Matching headlines to stocks uses company names; `data/aliases.txt` teaches it nicknames such as "Zomato" for Eternal. The movers and volume picks come from your own `docs/market.json`, so they only cover the stocks you track.

Check the feeds from your laptop any time:
```
python scripts\news.py --check
```
It prints OK or FAIL for every feed and the newest headlines. Remove or replace a feed in `data/feeds.txt` if it keeps failing. A failed feed is skipped; if every feed fails, the old `news.json` stays in place.

These are prompts to look, not recommendations, and a headline match can be wrong.

## What the signals mean

- **Sell**: price is at or under your stop (default 20% below what you paid, or your own stop price), or it fell 20% from its peak after gaining at least 10%.
- **Review**: it closed under its 200-day average 5 days in a row, or reached your target, or is 15% below its peak since you bought.
- **Room to add**: trend is up, price is not stretched above its 50-day average, and the holding is under 80% of your per-stock cap.
- **Hold**: no rule hit.

The 6 "ideas" checks: above the 200-day average, 50-day above 200-day, beat the Nifty over 12 months, within 20% of the 52-week high, volatility under 40%, and over Rs 10 crore traded a day. They pick stocks in a steady uptrend. They say nothing about whether the business is good.

## Tax note (not tax advice)

For listed shares where STT is paid, a sale more than 12 months after buying is long-term (12.5% above Rs 1.25 lakh of gains a year, as published for FY 2026-27). Within 12 months it is short-term (20%). The page counts the days and shows the date from which a sale would count as long-term. Confirm with a tax professional or your broker's statement.

## Files

```
docs/index.html, docs/logic.js   the page and its rules
docs/market.json                 made by the daily job
scripts/update.py                downloads prices, works out the numbers
scripts/news.py                  builds docs/news.json (headlines, markets, movers)
data/universe.txt                your stock list
data/feeds.txt                   news feeds (RSS)
data/aliases.txt                 nicknames for matching headlines to stocks
data/extra.txt                   ETFs and extras
data/screens.txt                 your own lists
.github/workflows/daily.yml      the schedule: 03:00 UTC (08:30 IST) news, 12:30 UTC (18:00 IST) everything, Mon-Fri
scripts/inline_logic.py          after editing docs/logic.js, copies it into docs/index.html
tests/                           python -m unittest discover -s tests ; node tests/test_logic.js
```
