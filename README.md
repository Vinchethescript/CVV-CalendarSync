# CVV-CalendarSync
[![README in Italian](https://img.shields.io/badge/README-in_Italian-184718)](README.it.md)

A Python program that syncs your Classeviva calendar into your Google Calendar so you can have all your events and homeworks in one place.

It uses the [`aiocvv`](https://github.com/Vinchethescript/aiocvv) library to fetch the events from Classeviva and the Google API to sync them into your Google Calendar.

![Demo](demo.gif)
###### *Note that the first two runs after setup ever might be buggy because of missing caches.*

## Installation and usage
> **Note**: This program works with Python 3.8 or higher.
1. Clone the repository;
2. Install the required packages with `pip install -Ur requirements.txt`;
3. [Setup a new project on the Google Cloud Platform](https://developers.google.com/calendar/api/quickstart/python) and download the `credentials.json` file to the root of the repository;
5. Copy the `example.env` file to `.env` and set the credentials for Classeviva;
6. To run it, simply run the `main.py` file with your favorite Python interpreter;
7. If running for the first time, you will be prompted to authenticate with Google and Classeviva. Follow the instructions on the terminal;
8. Check your calendar and enjoy!

Simple as that, isn't it?

> **Note**: This program will only work while the school year is active. If the year ends, you will get an error because `end must be greater than start`. If you still want to try it out, you can set the `FULL_YEAR` environment variable to 1 in the `.env` file, so it will fetch all the events from the beginning of the last year. For example, if the current year is 2021, it will fetch all the events from 2020 to 2021.

## Background usage
The program is designed to be run in the background, so you can use it in a server or in a Raspberry Pi, using whichever process manager you prefer (for example, systemd or pm2). The program will automatically sync your calendar every 30 minutes.

### Usage with pm2
You need to have `nodejs` and `npm` installed to install pm2.

All you need to do is install pm2 (`npm install -g pm2`) and run this program with `pm2 start main.py --name=cvvsync --interpreter=python3` (change `python3` to your Python interpreter, it also accepts absolute paths!).