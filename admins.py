# http://code.google.com/appengine/docs/python/mail/emailmessagefields.html
ADMIN_LIST = [('Robert Admin', 'admin@example.com')]
ADMIN_LIST_AS_STR = ['%s <%s>' % (name, email) for name, email in ADMIN_LIST]
ADMINS_TO = ', '.join(ADMIN_LIST_AS_STR)
