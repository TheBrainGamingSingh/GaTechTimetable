# celery -A GaTechTimetable.celery worker --pool=solo --loglevel=info
# rabbitmq-server -detached
import flask
from flask_sqlalchemy import SQLAlchemy
from celery import Celery

from apiclient import discovery
from oauth2client import client, file, tools

import httplib2
import datetime
from time import sleep

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as exp_cond
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup as BSoup

import factory

SCOPES = 'https://www.googleapis.com/auth/calendar'
CLIENT_SECRET_FILE = 'client_secret.json'
APPLICATION_NAME = 'GaTech Timetable'

app = factory.create_app()
celery = factory.create_celery(app)
db = SQLAlchemy(app)


class Timetable(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user = db.Column(db.String(20))
    timetable = db.Column(db.PickleType(protocol=4))

    def __init__(self, user, timetable):
        self.user = user
        self.timetable = timetable

    def __repr__(self):
        return '<user %r>' % self.user


@app.route('/')
def index():
    # sleep(2)
    return flask.render_template('index.html')


@app.route('/submit', methods=['POST', 'GET'])
def submit():
    usr = None
    pwd = None
    if flask.request.method == 'POST':
        usr = flask.request.form['username']
        pwd = flask.request.form['password']
        flask.session['username'] = usr
        task = get_timetable.apply_async(args=[usr, pwd])
        print({'status_url': flask.url_for('task_status', task_id=task.id)})
        return flask.jsonify({'status_url': flask.url_for('task_status', task_id=task.id)})
    return flask.redirect(flask.url_for('index'))


@app.route('/oauth2callback')
def oauth2callback():
    flow = client.flow_from_clientsecrets(
        '/Users/ryougi/PycharmProjects/GaTechTimetable/client_secret.json',
        scope='https://www.googleapis.com/auth/calendar',
        redirect_uri=flask.url_for('oauth2callback', _external=True)
    )
    if 'code' not in flask.request.args:
        auth_uri = flow.step1_get_authorize_url()
        return flask.redirect(auth_uri)
    else:
        auth_code = flask.request.args.get('code')
        credentials = flow.step2_exchange(auth_code)
        flask.session['credentials'] = credentials.to_json()
        return flask.redirect(flask.url_for('create_calendar'))


@app.route('/status/<task_id>')
def task_status(task_id):
    the_task = get_timetable.AsyncResult(task_id)
    the_state = the_task.state
    try:
        the_status = the_task.info.get('status')
    except AttributeError:
        the_status = the_task.result

    print(the_state, the_status)
    if the_state == 'PENDING':
        resp = {'status': 'Pending...', 'state': the_state}
    else:
        resp = {'status': the_status, 'state': the_state}

    return flask.jsonify(resp)


@app.route('/debug')
def debug():
    return flask.render_template('update.html')


@app.route('/create_calendar')
def create_calendar():
    if 'credentials' not in flask.session:
        return flask.redirect(flask.url_for('oauth2callback'))
    credentials = client.OAuth2Credentials.from_json(flask.session['credentials'])
    if credentials.access_token_expired:
        return flask.redirect(flask.url_for('oauth2callback'))
    return flask.render_template('update.html')


@app.route('/update_calendar')
def update_calendar():
    credentials = client.OAuth2Credentials.from_json(flask.session['credentials'])
    http_auth = credentials.authorize(httplib2.Http())
    service = discovery.build('calendar', 'v3', http=http_auth)

    calendar = \
        {
                'summary': 'GaTech Timetable',
                'timeZone': 'America/New_York'
        }

    created_calendar = service.calendars().insert(body=calendar).execute()
    calendar_id = created_calendar['id']
    flask.session['calendar_id'] = calendar_id
    username = flask.session['username']
    timetable = Timetable.query.filter_by(user=username).first()
    table = timetable.timetable
    print(table)
    for item in table:
        print(item)
        create_event(item)
    db.session.delete(timetable)
    db.session.commit()
    return 'All done!'


def create_event(event):
    credentials = client.OAuth2Credentials.from_json(flask.session['credentials'])
    calendar_id = flask.session.get('calendar_id')
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('calendar', 'v3', http=http)
    service.events().insert(calendarId=calendar_id, body=event).execute()


@celery.task(bind=True)
def get_timetable(self, username, password):
    url_cas = \
        'https://login.gatech.edu/cas/login?service=http://buzzport.gatech.edu/sso'
    url_oscar = \
        'https://buzzport.gatech.edu/render.UserLayoutRootNode.uP?uP_tparam=utf&' \
        'utf=%2Fcp%2Fip%2Flogin%3Fsys%3Dsct%26url%3Dhttps%3A%2F%2Foscar.gatech.edu/pls/bprod' \
        '%2Fztgkauth.zp_authorize_from_login'
    url_table = \
        'https://oscar.gatech.edu/pls/bprod/bwskfshd.P_CrseSchdDetl'

    self.update_state(state='PROGRESS', meta={'status': 'Initializing...'})
    driver = webdriver.PhantomJS(executable_path='/Users/ryougi/phantomjs')
    driver.get(url_cas)

    self.update_state(state='PROGRESS', meta={'status': 'Opening Georgia Tech website...'})
    input_username = driver.find_element_by_name('username')
    input_password = driver.find_element_by_name('password')
    input_username.send_keys(username)
    input_password.send_keys(password)

    self.update_state(state='PROGRESS', meta={'status': 'Logging into Georgia Tech Central Authentication System...'})
    input_password.submit()

    try:
        WebDriverWait(driver, 5).until(exp_cond.title_contains('BuzzPort'))
    except TimeoutException:
        self.update_state(state='FAILURE', meta={'status': 'Error: Log in failed.'})
        return 'Error: Log in failed.'

    driver.get(url_oscar)
    driver.get(url_table)
    select = driver.find_element_by_tag_name("select")
    all_options = select.find_elements_by_tag_name("option")

    self.update_state(state='PROGRESS', meta={'status': 'Fetching detailed schedule...'})
    for option in all_options:
        if option.text == 'Fall 2017':
            option.click()
            option.submit()
            break

    self.update_state(state='PROGRESS', meta={'status': 'Generating timetable...'})
    soup = BSoup(driver.page_source, 'html5lib')
    temp_name = soup.find_all(class_='captiontext')
    timetable = soup.find_all(class_='datadisplaytable')
    class_title = [0 for x in range(int(len(timetable) / 2))]

    for n in range(int(len(timetable) / 2)):
        class_title[n] = temp_name[2 * n].text
    class_begin_end_date = timetable[1].find_all('tr')[1].find_all('td')[4].text
    class_begin_date = class_begin_end_date.split(' - ')[0]
    class_end_date = class_begin_end_date.split(' - ')[1]

    begin_date = datetime.datetime.strptime(class_begin_date, '%b %d, %Y')
    end_date = datetime.datetime.strptime(class_end_date, '%b %d, %Y').strftime('%Y%m%d')
    begin_Monday = begin_date + datetime.timedelta(
        0 - datetime.datetime.strptime(class_begin_date, '%b %d, %Y').weekday())

    week_to_date = {'M': begin_Monday.strftime('%Y-%m-%d'),
                    'T': (begin_Monday + datetime.timedelta(1)).strftime('%Y-%m-%d'),
                    'W': (begin_Monday + datetime.timedelta(2)).strftime('%Y-%m-%d'),
                    'R': (begin_Monday + datetime.timedelta(3)).strftime('%Y-%m-%d'),
                    'F': (begin_Monday + datetime.timedelta(4)).strftime('%Y-%m-%d')}

    events = []
    for n in range(len(class_title)):
        current_timetable = timetable [2*n+1]. find_all ('tr')
        for k in range(1,len(current_timetable)):
            class_type = current_timetable[k].find_all('td')[0].text
            class_time = current_timetable[k].find_all('td')[1].text
            class_day = current_timetable[k].find_all('td')[2].text
            class_location = current_timetable[k].find_all('td')[3].text
            class_range = current_timetable[k].find_all('td')[4].text
            class_instructor = current_timetable[k].find_all('td')[6].text
            for item in class_day:
                date = week_to_date[item]
                begin_time = datetime.datetime.strptime(class_time.split(' - ')[0], "%I:%M %p")
                end_time = datetime.datetime.strptime(class_time.split(' - ')[1], "%I:%M %p")
                start = week_to_date[item]+'T'+ begin_time. strftime('%H:%M:%S')
                end = week_to_date[item]+'T'+ end_time. strftime('%H:%M:%S')
                if class_type == 'Lab':
                    class_name = class_title[n].split(' - ')[0] + ' ' \
                                 + class_type + ' - ' + class_title[n].split(' - ')[1]
                else:
                    class_name = class_title[n].split(' - ')[0] + ' - ' \
                                 + class_title[n].split(' - ')[1]
                event = {
                    'summary': class_name,
                    'location': class_location,
                    'start': {
                        'dateTime': start,
                        'timeZone': 'America/New_York',
                    },
                    'end': {
                        'dateTime': end,
                        'timeZone': 'America/New_York',
                    },
                    'recurrence': [
                        'RRULE:FREQ=WEEKLY;UNTIL=' + end_date + 'T235900Z'
                    ],
                    'reminders': {
                        'useDefault': False,
                        'overrides': [
                            {'method': 'popup', 'minutes': 5},
                        ],
                    },
                }
                events.append(event)
    user = Timetable(username, events)
    db.session.add(user)
    db.session.commit()
    self.update_state(state='SUCCESS',
                      meta={'status': 'Timetable successfully generated.'})
    return 'Finished.'


if __name__ == '__main__':
    import uuid
    app.secret_key = str(uuid.uuid4())
    app.run(threaded=True)