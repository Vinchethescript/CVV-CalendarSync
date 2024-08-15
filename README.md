# CVV-CalendarSync

A Python program that syncs your Classeviva calendar into your Google Calendar so you can have all your events and homeworks in one place.

It uses the [`aiocvv`](https://github.com/Vinchethescript/aiocvv) library to fetch the events from Classeviva and the Google API to sync them into your Google Calendar.

As of now, this is not ready to use as it's still in development, but you can still try it out if you want to. Just know that you may encounter lots of bugs and your calendar may be filled with duplicates.

## Installation
1. Clone the repository;
2. Install the required packages with `pip install -Ur requirements.txt`;
3. [Setup a new project on the Google Cloud Platform](https://developers.google.com/calendar/api/quickstart/python) and download the `credentials.json` file to the root of the repository;
5. Copy the `example.env` file to `.env` and fill in all the needed fields;
6. Run the program with your favorite Python interpreter.

Simple as that, isn't it?

## Background usage
The program is designed to be run in the background, so you can use it in a server or in a Raspberry Pi, using whichever process manager you prefer (for example, systemd or pm2). The program will automatically sync your calendar every 30 minutes.