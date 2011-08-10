# General libraries
from datetime import datetime

# App engine specific libraries
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

# App specific libraries
from library import ConvertToInterval
from library import InitGCAL
from library import UpdateSubscription
from models import UserCal


class MainHandler(webapp.RequestHandler):

  def get(self):
    """Updates every three hours."""
    now = ConvertToInterval(datetime.utcnow())
    GCAL = None

    all_users = UserCal.all()
    for user in all_users:
      if now in user.update_intervals:
        for link in user.calendars:
          if GCAL is None:
            GCAL = InitGCAL()
          UpdateSubscription(link, user.owner, GCAL)


application = webapp.WSGIApplication([
  ('/cron', MainHandler),
  ], debug=True)


if __name__ == '__main__':
  run_wsgi_app(application)
