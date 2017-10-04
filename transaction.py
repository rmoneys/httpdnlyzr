#!/usr/bin/python

import datetime
import re

onpremLogFormat = "%h %l %u %t \"%r\" %>s %b %T %k \"%{Referer}i\" \"%{User-Agent}i\" \"%{Content-Type}o\" %{JSESSIONID}C"
hostedLogFormat = "%{JiveClientIP}i %l %{X-JIVE-USER-ID}o %t \"%r\" %>s %b %T %k \"%{Referer}i\" \"%{User-Agent}i\" \"%{Content-Type}o\" %{JSESSIONID}C"
logFormat = onpremLogFormat
fmtStrExpr = re.compile(r"%(?:(>?\w)|\{([\w-]+)\}\w?)")

# The expressions in this map are for capturing transaction attributes, not validating them. Be careful not to make them too esclusive.
logFormatMap = {'h': r'(?:\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|[0-9a-fA-F:]+)'
    , 'JiveClientIP': r'(?:\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|[0-9a-fA-F:]+)'
    , 'l': '-'
    , 'u': '-'
    , 'X-JIVE-USER-ID': r'-?[0-9]*'
    , 't': r'\[(?P<date>.*) [+-]\d{4}\]'
    , 'r': r'(?P<method>[A-Z]+) (?P<path>(?:[^"\\]|\\.)*) [^"]*'
    , '>s': r'(?P<status>\d{3})'
    , 'b': r'(?P<size>-|\d+)'
    , 'T': r'(?P<time>\d+)'
    , 'k': r'\d+'
    , 'Referer': r'(?P<referer>(?:[^"\\]|\\.)*)'
    , 'User-Agent': r'(?P<userAgent>(?:[^"\\]|\\.)*)'
    , 'Content-Type': '(?P<contentType>[^"]*)'
    , 'JSESSIONID': '.*'
}
logExpression = re.compile(fmtStrExpr.sub(lambda m: logFormatMap[m.groups()[0] or m.groups()[1]], logFormat))
dateFormat="%d/%b/%Y:%H:%M:%S" # Consider the timezone to be local

oldLogExpression = re.compile('^.*\[(?P<date>.*) [+-]\d{4}\] "(?P<method>[A-Z]+) (?P<path>(?:[^"\\\]|\\\.)*) [^"]*" (?P<status>\d{3}) (?P<size>-|\d*) (?P<time>\d*) \d+ "(?P<referer>(?:[^"\\\]|\\\.)*)" "(?P<userAgent>(?:[^"\\\]|\\\.)*)" "(?P<contentType>[^"]*)" .*$')
# Example
# 155.201.35.178 - - [12/Nov/2014:00:00:56 +0000] "GET /__services/v2/rest/apps/v1/containersecuritytoken?_=1415750456371 HTTP/1.1" 200 134 13938 0 "https://pwc-spark.com/docs/DOC-37650" "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; WOW64; Trident/5.0)" "application/json" B26F4D8E89595991C6F2D193F15776BA 13588

class Transaction:
    def __init__(self, raw, node):
        matchedLine = logExpression.match(raw)

        if matchedLine:
            self.date = datetime.datetime.strptime(matchedLine.group('date'), dateFormat)
            self.method = matchedLine.group('method')
            self.path = matchedLine.group('path')
            self.status = matchedLine.group('status')
            self.size = 0 if matchedLine.group('size') == "-" else int(matchedLine.group('size'))
            self.time = int(matchedLine.group('time'))
            self.userAgent = matchedLine.group('userAgent')
            self.contentType = matchedLine.group('contentType')
            self.valid = True
        else:
            self.valid = False

        self.raw = raw
        self.node = node

    def isValid(self):
        return self.valid

    def getRaw(self):
        return self.raw

    def getNode(self):
        return self.node

    def isAuthError(self):
        return self.status.startswith("40")

    def isServerError(self):
        return self.status.startswith("50")

    def isError(self):
        return self.isAuthError() or self.isServerError()

    # This doesn't quite line up with JCA's userviews - this count is slightly larger.
    # JCA might be filtering out transactions from Jive IP addresses.
    def isUserview(self):
        return self.status == "200" and self.contentType == "text/html" and not self.userAgent == "WebInject"
        #return self.status == "200" and not self.userAgent == "WebInject"
        #return self.status == "200" and self.contentType == "text/html" and not self.userAgent in ["WebInject", "JiveClient"]

    def isAsyncview(self):
        return self.status == "200" and self.contentType == "application/json" and not self.userAgent == "WebInject"

    def isWrite(self):
        return self.method in ["PUT", "DELETE"] or self.method == "POST" and self.status == "302"
