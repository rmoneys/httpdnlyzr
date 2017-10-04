#!/usr/bin/python
import datetime
import re
import os
import logging

from textwrap import dedent

logger = logging.getLogger('profile')

class Node:
    def __init__(self, path):
        self.path = path
        self.children = {}

        self.reads = 0 # 0 means there's no page at this path
        self.executions = 0 # 0 means there's no page at this path

        self.readTime = 0
        self.executionTime = 0

        self.method = None
        self.contentType = None
        self.status = None

    def setTransaction(self, transaction):
        self.method = transaction.method
        self.contentType = transaction.contentType
        self.status = transaction.status

    def printNode(self, depth):
        indent = "  "
        for i in range(depth):
            indent = indent + "  "

        if self.reads > 0:
            print ("%s%s" % (indent, self.getDisplayPath())).ljust(80, "."), "%6d hits, %6d seconds, %s seconds per hit" % (self.reads, self.readTime, "{:6.2f}".format(self.readTime / float(self.reads)))
        else:
            print "%s%s" % (indent, self.path)

    def printNodeDetail(self):
        print "  Path: %s" % self.path
        print "  Total reads: %d" % self.reads
        print "  Total executions: %d" % self.executions
        print "  Total read time: %d" % self.readTime
        print "  Total execution time: %d" % self.executionTime

    def getDisplayPath(self):
        if not self.path:
            return "(server)"
        else:
            return self.path

    def addDescendant(self, descendant):
        self.children.append(descendant)

    def incrementReads(self, time):
        self.reads = self.reads + 1
        self.readTime = self.readTime + time
        self.incrementExecutions(time)

    def incrementExecutions(self, time):
        self.executions = self.executions + 1
        self.executionTime = self.executionTime + time

    def getReads(self):
        return self.reads

    def getExecutions(self):
        return self.executions

    def getChildren(self):
        return self.children

    def setMethod(self, method):
        self.method = method

    def getMethod(self):
        return self.method

    def setContentType(self, contentType):
        self.contentType = contentType

    def getContentType(self):
        return self.contentType

    def isLeaf(self):
        return self.reads > 0

class Tree:
    dateFormat = "%H:%M, %b %d"
    idPattern = re.compile("(?<=/)[0-9-]{4,}(?=/|$)")

    pathPatterns = ["/admin/**"
        , "/status/*"
        , "/message/*"
        , "/thread/*"
        , "/docs/*"
        , "/browserEvents/**"
        , "/**/blog/**"
        , "/**/blogs/**"
        , "/blogs/**"
        , "/community/**"
        , "/people/*"
        , "/people/*/activity"
        , "/people/*/content"
        , "/people/*/people"
        , "/people/*/avatar**"
        , "/people/*/status**"
        , "/bookmarks/*"
        , "/groups/*"
        , "/groups/*/activity"
        , "/groups/*/content"
        , "/groups/*/overview"
        , "/groups/*/people"
        , "/groups/*/projects/*"
        , "/docs/*"
        , "/projects/*"
        , "/polls/*"
        , "/photos/*"
        , "/photoAlbums/*"
        , "/events/*"
        , "/ideas/*"
        , "/videos/*"
        , "/__services/v2/rest/morelikethis/2/*/type/2"
        , "/__services/v2/rest/morelikethis/102/*/type/102"
        , "/__services/v2/rest/morelikethis/700/*/type/700"
        , "/__services/v2/rest/morelikethis/801/*/type/801"
        , "/__services/v2/rest/tags/search/*"
        , "/__services/v2/rest/legacy_token/*"
        , "/__services/v2/rest/message/*/*"
        , "/__services/v2/rest/discussions/*/question"
        , "/__services/v2/rest/office/api/getComments/*"
        , "/__services/v2/rest/office/status/*"
        , "/__services/v2/rest/comments/102/*"
        , "/__services/v2/rest/polls/*/*/0"
        , "/__services/v2/rest/readtracking/*/*/read"
        , "/__services/v2/rest/socialgroups/*/members"
        , "/__services/v2/rest/draft/*"
        , "/__services/v2/rest/browserEvents/*"
        , "/__services/v2/rest/activity-stream/fullcontent/**"
        , "/servlet/JiveServlet/downloadBody/**"
        , "/servlet/JiveServlet/downloadImage/**"
        , "/servlet/JiveServlet/download/**"
        , "/servlet/JiveServlet/showImage/**"
        , "/servlet/JiveServlet/previewBody/**"
        , "/api/core/v3/activities/recent/*"
        , "/api/core/v3/activities/frequent/*"
        , "/api/core/v3/contents/*"
        , "/api/core/v3/i18n/minify/*"
        , "/api/core/v3/places/*"
        , "/api/core/v3/places/*/activities"
        , "/api/core/v3/places/*/followingIn"
        , "/api/core/v3/people/*"
        , "/api/core/v3/people/username/*"
        , "/api/core/v3/people/*/avatar"
        , "/api/core/v3/people/*/followingIn"
        , "/__services/eapis/v1/image/avatar/*"
        , "/__services/eapis/v2.1/content/preview/**"
        , "/__services/eapis/v2.1/container/*/*/categories"
        , "/__services/eapis/v2.1/document/*/coauthors"
        , "/__services/eapis/v2.1/document/*/init"
        , "/__services/eapis/v2.1/document/*/meta"
        , "/__services/eapis/v2.1/document/*/update/meta"
        , "/__services/eapis/v2.1/document/*/versions/meta"
        , "/__services/eapis/v2.1/user/details/*"
        , "/__services/eapis/v2.1/user/*/recentActivity"
        , "/__services/v2/rest/activity-stream/fillinthegaps/**"
        , "/__services/v2/rest/activity-stream/fullreplies/**"
        , "/__services/v2/rest/activity-stream/profile/*"
        , "/__services/v2/rest/emention/search/*"
        , "/__services/v2/rest/recommendation/userstrendingcontent/**"
        , "/__services/v2/rest/rating/**"
        , "/__services/v2/rest/users/search/*"
        , "/__services/v2/rest/morelikethis/**"
        , "/__services/v2/rest/users/*/related/common/count"
        , "/*/resources/scripts/gen/*"
        , "/themes/**"
        , "/*/plugins/**"
        , "/resources/statics/*/*"
    ]

    # Writes seen in 4.5
    # /post.jspa - Thread and thread reply; POST, 302, text/html
    # /doc-create.jspa - Document creation; POST, 302, text/html 
    # /blogs-create-post.jspa - Blog post creation: POST, 302, text.html
    # /__services/v2/rest/comments/102/* - Document comment creation; POST, 200, application/json
    # /__services/v2/rest/comments/38/* - Blog post comment creation; POST, 200, application/json

    # Writes seen in 7.0
    # /__services/v2/rest/message/{threadID}/{messageID} - Message creation; POST, 200, application/json
    # /__services/v2/rest/discussion - Thread creation; POST, 200, application/json

    loadTestingRequests45 = ["/post.jspa"
        , "/doc-create.jspa"
        , "/doc-upload.jspa"
        , "/thread/*"
        , "/message/*"
        , "/docs/*"
        , "/doc-comments.jspa"
        , "/search.jspa"
        , "/groups/*"
        , "/index.jspa"
        , "/community/**"
        , "/spotlight-search.jspa"
        , "/people/*"
        , "/**/blog**"
        , "/comment-list.jspa"
        , "/profile-short.jspa"
        , "/status/*"
        , "/polls/*"
    ]

    loadTestingPathPatterns = ["/post.jspa"
        , "/doc-create.jspa"
        , "/doc-upload.jspa"
        , "/blogs-create-post.jspa"
        , "/welcome"
        , "/__services/v2/rest/comments/102/*"
        , "/__services/v2/rest/comments/38/*"
        , "/thread/*"
        , "/message/*"
        , "/docs/*"
        , "/doc-comments.jspa"
        , "/search.jspa"
        , "/api/core/v3/search/contents"
        , "/api/core/v3/search/people"
        , "/api/core/v3/activities/recent/*"
        , "/groups/*"
        , "/community/**"
        , "/spotlight-search.jspa"
        , "/people/*"
        , "/**/blog**"
        , "/comment-list.jspa"
        , "/profile-short.jspa"
        , "/status/*"
        , "/polls/*"
    ]

    def __init__(self, transactionGenerator, context, startDate, stopDate):
        self.context = context
        self.root = Node("")
        self.leaves = []
        sitePathPatterns = ["/%s%s" % (context, p) for p in Tree.pathPatterns] if context else Tree.pathPatterns
        sitePathREPatterns = [(re.compile("^%s$" % re.sub("\*{1,2}|/", lambda x: {"**": ".*", "*": "[^/]+", "/": "/+"}[x.group()], s)), s) for s in sitePathPatterns]
        queryStart = re.compile('\?')
        pathDelimiter = re.compile('/+')
        skippedCount = 0
        totalCount = 0

        firstDate = datetime.datetime.max
        lastDate = datetime.datetime.min

        for transaction in transactionGenerator:
            if transaction.isError():
                logger.debug("Skipping transaction with HTTP error status, %s:\n\t%s", transaction.status, transaction.getRaw())
                skippedCount += 1
            else:
                if transaction.date < firstDate:
                    firstDate = transaction.date
                if transaction.date > lastDate:
                    lastDate = transaction.date

                resourceURL = queryStart.split(transaction.path, maxsplit=1)[0]
                simplifiedURL = Tree.collapsePath(resourceURL, sitePathREPatterns)
                steps = pathDelimiter.split(simplifiedURL)
                self.addLeaf(self.root, steps[1:], transaction)
            totalCount += 1

        logger.info("Skipped %d transactions (%.2f%%)", skippedCount, 100. * skippedCount / totalCount)

        # Fix the start & stop dates
        if not startDate or firstDate < startDate:
            self.startDate = firstDate
        else:
            self.startDate = startDate

        if not stopDate or lastDate >= stopDate:
            self.stopDate = lastDate + datetime.timedelta(minutes=1)
        else:
            self.stopDate = stopDate
            
    def addLeaf(self, parent, path, transaction):
        if len(path) > 0:
            parent.incrementExecutions(transaction.time)

            step = path[0]

            children = parent.getChildren()
            if children.has_key(step):
                thisNode = children[step]
            else:
                thisNode = Node(parent.path + "/" + step)
                children[step] = thisNode

            self.addLeaf(thisNode, path[1:], transaction)
        else:
            if parent.getReads() == 0:
                self.leaves.append(parent)
                parent.setTransaction(transaction)
            parent.incrementReads(transaction.time)

    def printSummary(self): 
        print "Transactions ordered by the sum of executions and reads."
        Tree.printTree(self.root, 0, 10)

        print "Root statistics"
        self.root.printNodeDetail()

        print "Most time consuming"
        self.leaves.sort(key=lambda x: x.readTime, reverse=True)
        for l in self.leaves[:20]:
            l.printNode(0)

        print "Highest throughput"
        self.leaves.sort(key=lambda x: x.reads, reverse=True)
        for l in self.leaves[:20]:
            l.printNode(0)

        print "Slowest average transaction time"
        self.leaves.sort(key=lambda x: x.readTime / float(x.reads), reverse=True)
        for l in self.leaves[:20]:
            l.printNode(0)

        print "Standard load testing profile"
        siteLoadTestingPaths = ["/%s%s" % (self.context, p) for p in Tree.loadTestingPathPatterns] if self.context else Tree.loadTestingPathPatterns
        Tree.printLoadTestingProfile(self.leaves, siteLoadTestingPaths)

        print "Dynamic load testing profile"
        Tree.printDynamicLoadTestingProfile(self.leaves)

    def writeMostTimeConsumingPlot(self, workDir): 
        dataFile = self.writeMostTimeConsumingPlotData(workDir)
        scriptFile = self.writePlotScript(workDir, "Profile of Web Transaction Time", dataFile)

        return "gnuplot %s" % scriptFile

    def writeHighestThroughputPlot(self, workDir): 
        dataFile = self.writeHighestThroughputPlotData(workDir)
        scriptFile = self.writePlotScript(workDir, "Profile of Web Transaction Frequency", dataFile)

        return "gnuplot %s" % scriptFile

    def writeMostTimeConsumingPlotData(self, workDir): 
        # Show the 10 most time consuming transactions in a pie chart
        dataFile = os.path.join(workDir, "mostTimeConsuming.dat")
        self.leaves.sort(key=lambda x: x.readTime, reverse=True)
        with open (dataFile, "w") as dataFileHandle:
            # Header
            print >>dataFileHandle, "%80s Percent" % "Path"

            totalOfRest = 0
            for leaf in self.leaves:
                percent = leaf.readTime / float(self.root.executionTime)

                # Top with 2% or more
                if not percent < 0.02:
                    print >>dataFileHandle, "%80s   %0.3f" % (leaf.getDisplayPath(), percent)
                else:
                    totalOfRest += leaf.readTime

            print >>dataFileHandle, "%80s   %0.3f" % ("other", totalOfRest / float(self.root.executionTime))
        return dataFile

    def writeHighestThroughputPlotData(self, workDir): 
        # Show the 10 most time consuming transactions in a pie chart
        dataFile = os.path.join(workDir, "highestThroughput.dat")
        self.leaves.sort(key=lambda x: x.reads, reverse=True)
        with open (dataFile, "w") as dataFileHandle:
            # Header
            print >>dataFileHandle, "%80s Percent" % "Path"

            totalOfRest = 0
            for leaf in self.leaves:
                percent = leaf.reads / float(self.root.executions)

                # Top with 2% or more
                if not percent < 0.02:
                    print >>dataFileHandle, "%80s   %0.3f" % (leaf.getDisplayPath(), percent)
                else:
                    totalOfRest += leaf.reads

            print >>dataFileHandle, "%80s   %0.3f" % ("other", totalOfRest / float(self.root.executions))
        return dataFile

    def writePlotScript(self, workDir, title, dataFile): 
        scriptFile = os.path.join(workDir, Tree.variableName(title) + ".gnu")
        with open (scriptFile, "w") as scriptFileHandle:
            print >>scriptFileHandle, dedent("""
                reset
                unset key; set border 0; unset tics; unset colorbox; set size 0.51,0.85; set origin 0.24, 0
                set title "%s from %s to %s" offset char 0, char 2
                set urange [0:1]
                set vrange [0:1]
                set macro
                sum = 0.25
                n = 0
                PLOT = "splot 0, 0, 1/0 with pm3d"
                LABEL = ""

                set palette rgbformulae 33,13,10 negative

                g(x,y,n) = \\
                sprintf(", \\
                cos((%%.3f+%%.3f*u)*2*pi)*v, \\
                sin((%%.3f+%%.3f*u)*2*pi)*v, \\
                %%d @PL", x, y, x, y, n)

                lab(alpha, x) = sprintf("set label \\"%%s\\" at %%.2f, %%.2f %%s front;", \\
                x, 1.1*cos(alpha), 1.1*sin(alpha), alpha < 4.78 ? 'right' : 'left')

                f(x) = (PLOT = PLOT.g(sum, x, n), \\
                LABEL = LABEL.lab(2*pi*sum+pi*x, escapeAll(stringcolumn(1)).sprintf(" (%%.1f%%%%)", $2 * 100)), \\
                sum = sum+x, n = n + 1, x)

                escapeAll(x) = escape(escape(x, "_"), "@")
                escape(x, y) = (i = strstrt(x, y), i > 0 ? x[1:i - 1]."\\\\\\\\".y.escape(x[i + 1:*], y) : x)

                # There are many ways to draw a pie chart in Gnuplot 4.6. None are very straight forward, but this is probably the
                # most succinct, despite being a hack. The following plot command is solely to build the strings, LABEL and PLOT.
                # An alternative is to plot each slice one-by-one in a multiplot.
                plot '%s' every ::1 u 0:(f($2))

                PL = "with pm3d"
                set parametric; set pm3d map; set border 0; unset tics; unset colorbox;
                eval(LABEL)
                eval(PLOT)
            """ % (title, self.startDate.strftime(Tree.dateFormat), self.stopDate.strftime(Tree.dateFormat), dataFile))
        return scriptFile

    def getTotalExecutionTime(self):
        return self.root.executionTime

    @staticmethod
    def variableName (name):
        t = [x.title() for x in name.split()]
        return t[0].lower() + "".join(t[1:])

    @staticmethod
    def printLoadTestingProfile (nodes, paths):
        testRequests = [x for x in nodes if x.path in paths]
        totalReads = sum([x.reads for x in testRequests])
        for l in testRequests:
            print "  %s %6d hits, %s" % (l.getDisplayPath().ljust(100), l.reads, "{:5.2f}%".format(l.reads / float(totalReads) * 100))

    @staticmethod
    def printDynamicLoadTestingProfile (nodes):
        topTextHTML = sorted([n for n in nodes if n.getContentType() == "text/html"], cmp=lambda x, y: x.readTime - y.readTime, reverse=True)[:20]
        totalReads = reduce(lambda x, y: x + y, [x.reads for x in topTextHTML])
        loadTestRequests = []
        loadTestReads = 0
        for t in topTextHTML:
            if t.reads > totalReads / 300:
                loadTestRequests.append(t)
                loadTestReads += t.reads
        for t in sorted(loadTestRequests, cmp=lambda x, y: x.reads - y.reads, reverse=True):
            print "  {:s} {:6d} hits, {:5.2f}%".format(t.getDisplayPath().ljust(100), t.reads, t.reads / float(loadTestReads) * 100)

    @staticmethod
    def collapsePath(path, sitePathREPatterns):
        for c in sitePathREPatterns:
            if c[0].match(path):
                return c[1]
        return Tree.idPattern.sub("*", path)

    @staticmethod
    def printTree(node, depth, limit):
        node.printNode(depth)
        children = node.getChildren().values()

        if len(children) > 0 and depth < limit:
            children.sort(key=lambda x: x.getReads() + x.getExecutions(), reverse=True)
            
            for c in children:
                Tree.printTree(c, depth + 1, limit)
