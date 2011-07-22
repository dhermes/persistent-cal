import os
import urllib2

import gdata
import icalendar

from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app


class MainHandler(webapp.RequestHandler):
  """Handles / as well as redirects for login required"""
  def get(self):
    path = os.path.join(os.path.dirname(__file__), 'templates', 'index.html')
    self.response.out.write(template.render(path, {}))


class VerifyHandler(webapp.RequestHandler):
  """Handles / as well as redirects for login required"""
  def get(self):
    path = os.path.join(os.path.dirname(__file__),
                        'googlef7560eebc24762bb.html')
    self.response.out.write(template.render(path, {}))


class Throw404(webapp.RequestHandler):
  """Catches all non-specified (404) requests"""
  def get(self):
    self.error(404)
    path = os.path.join(os.path.dirname(__file__), 'templates', '404.html')
    self.response.out.write(template.render(path, {}))


application = webapp.WSGIApplication([
  ('/googlef7560eebc24762bb.html', VerifyHandler),
  ('/', MainHandler),
  ('/.*', Throw404),
  ], debug=True)


def main():
    run_wsgi_app(application)


if __name__ == '__main__':
    main()
