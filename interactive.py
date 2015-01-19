#!/usr/bin/python

# Copyright (C) 2010-2012 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Handlers for interactive admin console (web-based).

These templates are largly borrowed from:
$PYTHON_LIB/google/appengine/ext/admin/templates/
and these handlers from
$PYTHON_LIB/google/appengine/ext/admin/__init__.py
"""


__author__ = 'daniel.j.hermes@gmail.com (Daniel Hermes)'


# General libraries
import cStringIO
import sys
import traceback

# App engine specific libraries
from google.appengine.ext.admin import get_xsrf_token
from google.appengine.ext.admin import xsrf_required
import webapp2

# App specific libraries
from handler_utils import ExtendedHandler


INTERACTIVE_PATH = '/admin/interactive'
INTERACTIVE_EXECUTE_PATH = INTERACTIVE_PATH + '/execute'


class InteractivePageHandler(ExtendedHandler):
  """Shows our interactive console HTML."""

  def get(self):  # pylint:disable-msg=C0103
    """Serves interactive console."""
    application_name = self.request.environ.get('APPLICATION_ID', '')
    xsrf_token = get_xsrf_token()
    self.RenderResponse('interactive.html',
                        application_name=application_name,
                        interactive_execute_path=INTERACTIVE_EXECUTE_PATH,
                        xsrf_token=xsrf_token)


class InteractiveExecuteHandler(ExtendedHandler):
  """Executes the Python code submitted in a POST within this context.

  For obvious reasons, this should only be available to administrators
  of the applications.
  """

  @xsrf_required
  def post(self):  # pylint:disable-msg=C0103
    """Handles POSTed code from interactive console."""
    save_stdout = sys.stdout
    results_io = cStringIO.StringIO()
    try:
      sys.stdout = results_io


      code = self.request.get('code')
      code = code.replace('\r\n', '\n')

      try:
        compiled_code = compile(code, '<string>', 'exec')
        exec(compiled_code, globals())  # pylint:disable-msg=W0122
      except Exception:  # pylint:disable-msg=W0703
        traceback.print_exc(file=results_io)
    finally:
      sys.stdout = save_stdout

    results = results_io.getvalue()
    self.RenderResponse('interactive-output.html', output=results)


APPLICATION = webapp2.WSGIApplication([
    (INTERACTIVE_PATH, InteractivePageHandler),
    (INTERACTIVE_EXECUTE_PATH, InteractiveExecuteHandler)],
    debug=True)
