# GaTechTimetable

This is a web application for Georgia Tech students to import their time schedules into Google Calendar. 

It is currently hosted on https://www.doki-feeling.com.

## Requirements

`pip3 install flask flask_sqlalchemy celery selenium google-api-python-client httplib2 bs4 html5lib`

`celery` requires [RabbitMQ](https://www.rabbitmq.com) and [SQLite](https://www.sqlite.org).

`selenium` requires [PhantomJS](http://phantomjs.org/download.html).

## Notes

Since I haven't required the GeorgiaTech official API for the registration system, the current way to get the schedule is simulating a user login. So the web page will require the username AND password of the user, which is quite unsafe even though the application does not store the information.

Georgia Tech is also enabling 2-step authentication, which requires additional work to be done in the future.
