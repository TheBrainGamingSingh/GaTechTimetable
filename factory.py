from flask import Flask
from celery import Celery


def create_app():
    app = Flask('GaTechTimetable')
    app.config['DEBUG'] = False
    app.config['CELERY_BROKER_URL'] = 'amqp://username:password@localhost/timetable'
    app.config['CELERY_RESULT_BACKEND'] = 'rpc://'
    app.config['CELERY_TRACK_STARTED'] = False
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////path_to_database'
    return app


def create_celery(app=None):
    app = app or create_app()
    celery = Celery(app.import_name, broker=app.config['CELERY_BROKER_URL'])
    celery.conf.update(app.config)
    task_base = celery.Task

    class ContextTask(task_base):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return task_base.__call__(self, *args, **kwargs)

    celery.Task = ContextTask
    return celery

