#!/usr/bin/python
#/usr/local/bin/python2.7
#
# Requirements
#   Python [2.7.5, 3)
#   Gnuplot >= 4.6
#   Terminal such as X11 or aquaterm (OSX)
#
# Changes for linux
#   Specify Python version because minimum for this script is 2.7.5
#   gunzip cannot executed in a shell (logFile())
#
# TODO
#   Add exclusions located here: https://brewspace.jiveland.com/docs/DOC-179235
#   optparse is deprecated; use argparse instead (new in version 3.2)

import datetime
import json
import locale
import math
import md5
import os
import re
import subprocess
import logging
import multiprocessing
import textwrap
import Queue # Changed to "queue" in Python 3

from optparse import OptionParser

from stats import Stats
from transaction import Transaction
from profile import Tree

dateFormat="%d/%b/%Y:%H:%M:%S" # Consider the timezone to be local
locale.setlocale(locale.LC_ALL, 'en_US')

logger = logging.getLogger('main')

# Global multiprocessing objects
# This is a simplier alternative then using a manager to start a server and provide proxies to server objects...
transactionQueue = multiprocessing.Queue()
accessLogPathQueue = multiprocessing.Queue()
logFilesProcessed = multiprocessing.Value('b', False)

def main():
    # Define the CLI
    parser = OptionParser(usage="usage: %prog [options] -w {working directory} [log directory]...")
    parser.add_option("-s", "--start", dest="startDate", help="String representing the start date in the format used by the log file, e.g.: 12/May/2014:09:00")
    parser.add_option("-t", "--stop", dest="stopDate", help="String representing the stop date in the format used by the log file, e.g.: 12/May/2014:18:00")
    parser.add_option("-w", "--working_dir", dest="workDir", help="Path to directory to usPath to directory for files created by this script")
    parser.add_option("-M", "--by_minute", dest="hourly", action="store_false", default=True, help="Plot pageviews by the minute (hour is the default)")
    parser.add_option("-f", "--force", dest="force", action="store_true", default=False, help="Force access logs to be processed again. Takes precedence over -i")
    parser.add_option("-d", "--days", dest="days", action="store_true", default=False, help="Plot pageviews by day for each node")
    parser.add_option("-n", "--no-filter", dest="filterLogs", action="store_false", default=True, help="Do not filter log files by name")
    parser.add_option("-i", "--ignore", dest="ignore", action="store_true", default=False, help="Don't process access logs")
    parser.add_option("-e", "--environment", dest="environment", default="Production", help="The string representing the target environment")
    parser.add_option("-m", "--match", dest="match", help="Select transactions by pattern")
    parser.add_option("-p", "--percentile", action="store_true", dest="percentile", default=False, help="Plot the 95th percentile transaction time")
    parser.add_option("-H", "--host", dest="host", default="webapp node", help="Installation host")
    parser.add_option("-q", "--quiet", action="store_true", dest="quiet", default=False, help="Turn down the logging")
    parser.add_option("-v", "--verbose", action="store_true", dest="verbose", default=False, help="Turn up the logging")
    parser.add_option("-u", "--tree", action="store_true", dest="tree", default=False, help="Do not plot; print textual requst tree instead")
    parser.add_option("-c", "--context", dest="context", default="", help="Site context")
    parser.add_option("-a", "--apitime", action="store_true", dest="apitime", default=False, help="Plot APIview time instead of Userview time")
    parser.add_option("-A", "--agent", dest="agent", help="Filter out transactions without a matching user agent")

    (options, args) = parser.parse_args()

    # Process arguments
    startDate = None if not options.startDate else datetime.datetime.strptime(options.startDate, "%d/%b/%Y:%H:%M")
    stopDate = None if not options.stopDate else datetime.datetime.strptime(options.stopDate, "%d/%b/%Y:%H:%M")
    dataFilePath = "%s/pageviews.dat" % options.workDir 
    pageviewsByDayDataFilePath = "%s/pageviews_by_day" % options.workDir 
    infoFilePath = "%s/info.json" % options.workDir
    pathRE = None if not options.match else re.compile(options.match)

    if options.tree or options.days:
        options.force = True

    if options.quiet:
        setLoggingLevel(logging.WARN)
    elif options.verbose:
        setLoggingLevel(logging.DEBUG)
    else:
        setLoggingLevel(logging.INFO)

    context = options.context.strip("/")

    errorMsgs = validateOptions(options.workDir, startDate, stopDate, parser.get_usage())
    if errorMsgs:
        print "Unable to proceed. Adjustment your command or environment by the following and try again."
        for i in range(len(errorMsgs)):
            print "  {:2d}) {:s}".format(i + 1, errorMsgs[i])
        print
        exit(1)

    accessLogPaths = getAccessLogs(args, startDate, stopDate, options.filterLogs)

    if shouldRecalculate(options, infoFilePath, dataFilePath, accessLogPaths):
        logger.info("Plot data is stale or missing. Recaculating...")

        if not accessLogPaths:
            logger.error("No access logs found. Be sure their names match the pattern, ^jive-httpd(?:-ssl)?-access\.log.*")
            exit(2)

        for p in accessLogPaths:
            logger.info("Will process %s", p)

        transactionGenerator = processLogFiles(accessLogPaths, startDate, stopDate, pathRE, options.agent)

        if options.tree:
            # Traffic Profiling
            transactionTree = Tree(transactionGenerator, context, startDate, stopDate)

            if transactionTree.getTotalExecutionTime() < 1:
                logger.error("Not enough transactions met the critieria. Try adjusting the time frame.")
                exit(3)

            transactionTree.printSummary()
            mostTimeConsuming = transactionTree.writeMostTimeConsumingPlot(options.workDir)
            mostFrequent = transactionTree.writeHighestThroughputPlot(options.workDir)

            print "View profile of web transaction time by executing the following command."
            print mostTimeConsuming

            print "View profile of web transaction frequency by executing the following command."
            print mostFrequent

        else:
            stats = getStats(transactionGenerator)
            if stats.isEmpty():
                logger.error("No transactions were processed")
                exit(4)

            printStats(stats)

            if options.days:
                gnuFile = writePageviewsByDayPlotData(stats, startDate, stopDate, pageviewsByDayDataFilePath, options.environment)

                print "View pageviews by day by executing the following command."
                print "gnuplot {0}".format(gnuFile)

            else:
                if not startDate or not stopDate:
                    # Set date range if one is not specified
                    hours = stats.getPeakHours(8)
                    startDate = hours[0].getDate()
                    stopDate = hours[-1].getDate() + datetime.timedelta(hours=1)
                else:
                    hours = stats.getHours(startDate, stopDate)

                minutes = stats.getMinutes(startDate, stopDate)

                # Plotting
                writePageviewPlotData(hours, minutes, startDate, stopDate, dataFilePath, options.hourly)
                writePlotInfo(options, minutes, startDate, stopDate, infoFilePath)

    if not options.tree and not options.days:
        with open (infoFilePath, "r") as infoFileHandle:
            plotInfo = json.load(infoFileHandle)
            printPlotInfo(plotInfo)

        # Plotting
        plotPageviews(plotInfo, options, dataFilePath)

# Filter out old log files
def filterAccessLogs(accessLogPaths, startDate, stopDate):
    logFileNameDateFormat="%Y%m%d"
    logFileFormat = re.compile('.*/jive-httpd(?:-ssl)?-access\.log-(?P<date>\d{8})(?:.gz)?$')
    numberOfWeeks = 2

    datePaths = []

    for logFile in accessLogPaths:
        match = logFileFormat.match(logFile)
        if match:
            # Sadly the date of the log entries is a day less than the date in the log file name
            logDate = datetime.datetime.strptime(match.group('date'), logFileNameDateFormat) - datetime.timedelta(days=1)
            datePaths.append((logDate, logFile))
        else:
            datePaths.append((None, logFile))

    maxDate = max(datePaths, key=lambda dp: datetime.datetime.min if not dp[0] else dp[0])[0]

    # In case no dates can be parsed from the log file names
    if not maxDate:
        maxDate = datetime.datetime.min

    if not startDate:
        startDate = maxDate - datetime.timedelta(weeks=numberOfWeeks) if maxDate > datetime.datetime.min else datetime.datetime.min

    if not stopDate:
        stopDate = maxDate + datetime.timedelta(days=1) if maxDate > datetime.datetime.min else datetime.datetime.max

    return [dp[1] for dp in datePaths if not dp[0] or dp[0] < stopDate and dp[0] >= datetime.datetime(startDate.year, startDate.month, startDate.day)]

def isDataStale(infoFilePath, dataFilePath, logFileTime):
    if not os.path.isfile(dataFilePath) or not os.path.isfile(infoFilePath): 
        return True

    infoFileTime = os.path.getmtime(infoFilePath)
    if not logFileTime < infoFileTime:
        return True

    return False

def getOptionDigest(options):
    return md5.new( "%s - %s, %s" % ("X" if not options.startDate else options.startDate, "X" if not options.stopDate else options.stopDate, "by hour" if options.hourly else "by minute")).hexdigest()

def optionsMatch(options, info):
    return info.has_key('optionDgst') and info['optionDgst'] == getOptionDigest(options)

def logFile(path):
    if path.endswith('.gz'):
        return subprocess.Popen(["gunzip", "--stdout", path], shell=False, bufsize=-1, stdout=subprocess.PIPE).stdout
    else:
        return open(path, 'r')

def writePageviewPlotData(hours, minutes, startDate, stopDate, pageviewDataPath, hourly):
    pvDistribution = []

    hour_iter = iter(hours)
    h = hour_iter.next()
    for m in minutes:
        if hourly:
            if not m.getDate() - h.getDate() < datetime.timedelta(hours=1):
                h = hour_iter.next()
            pvDistribution.append((m.getDate()
                , h.getUserviewCount()
                , h.getApiviewCount()
                , m.getUserviewAvgTime()
                , m.getAsyncviewAvgTime()
                , m.get95PercentileUserviewTime()
                , m.get95PercentileAsyncviewTime()
                , m.getStdDevUserviewTime()))
        else:
            pvDistribution.append((m.getDate()
                , m.getUserviewCount()
                , m.getApiviewCount()
                , m.getUserviewAvgTime()
                , m.getAsyncviewAvgTime()
                , m.get95PercentileUserviewTime()
                , m.get95PercentileAsyncviewTime()
                , m.getStdDevUserviewTime()))

    # Create data file for gnuplot
    epoch = datetime.datetime.utcfromtimestamp(0)
    with open (pageviewDataPath, "w") as dataFileHandle:
        print >>dataFileHandle, "   Timestamp  Userviews  APIviews  Avg User Tx Time  Avg API Tx Time  Userview Pcnt Time  API Pcnt Time  User Tx Std Deviation"
        for i in range(len(pvDistribution)):
            pvPoint = pvDistribution[i]
            print >>dataFileHandle, "%12d %10d %9d %17.2f %16.2f %19d %14d %22.2f" % ((pvPoint[0] - epoch).total_seconds(), pvPoint[1], pvPoint[2], pvPoint[3], pvPoint[4], pvPoint[5], pvPoint[6], pvPoint[7])

def writePageviewsByDayPlotData(stats, startDate, stopDate, dataFilePath, environment):
    dayDelta = datetime.timedelta(days=1)

    days = [day for day in stats.getDays(startDate, stopDate) if day.getPageviewCount() > 100] # List comprehensions preserve order
    firstDay = days[0].getDate()
    lastDay = days[-1].getDate() + dayDelta
    currentDay = firstDay
    nextDay = firstDay + dayDelta

    nodeIDs = stats.getAllNodes().keys()
    nodeIDs.sort()
    with open (dataFilePath + ".dat", "w") as dataFileHandle:
        print >>dataFileHandle, "       Webapp  Userviews  Asyncviews"

        while currentDay < lastDay:
            print >>dataFileHandle
            print >>dataFileHandle, currentDay.strftime('"%a, %b %d"')

            # Print data for the first node
            nodeStats = stats.getNode(nodeIDs[0])
            nodeDays = nodeStats.getDays(currentDay, nextDay)
            if nodeDays:
                userviews = nodeDays[0].getUserviewCount()
                apiviews = nodeDays[0].getApiviewCount()
            else:
                userviews = 0
                apiviews = 0

            print >>dataFileHandle, "%s %10d %11d" % (currentDay.strftime('"%a, %b %d"'), userviews, apiviews)

            for nodeStats in [stats.getNode(nodeID) for nodeID in nodeIDs[1:]]:
                nodeDays = nodeStats.getDays(currentDay, nextDay)
                if nodeDays:
                    userviews = nodeDays[0].getUserviewCount()
                    apiviews = nodeDays[0].getApiviewCount()
                else:
                    userviews = 0
                    apiviews = 0

                print >>dataFileHandle, '           "" %10d %11d' % (userviews, apiviews)

            currentDay = nextDay
            nextDay = currentDay + dayDelta

    with open (dataFilePath + ".gnu", "w") as gnuFileHandle:
        # If there's more than one node draw a clustered graph
        if len(nodeIDs) > 1:
            gnuScript = textwrap.dedent("""
                set title "Daily Load for {0:d} {1:s} Webapp Nodes"

                set xlabel "Date"
                set ylabel "Pageviews per Day"

                set nokey

                set grid ytics
                set xtics nomirror rotate by -45 scale 0 font ",8"

                set style data histogram
                set style histogram clustered gap 1
                set style histogram rows

                set style fill solid border -1

                plot newhistogram, "{2:s}" every ::1:1::1 using 2:xtic(1) lc rgb "#F01010" title "User Views", "" every ::1:1::1 using 3 lc rgb "#FFA500" title "API Views", \\
            """).format(len(nodeIDs), environment, dataFilePath + ".dat").strip()

            print >>gnuFileHandle, gnuScript

            for i in range((lastDay - firstDay).days)[1:]:
                print >>gnuFileHandle, 'newhistogram, "" every ::1:{0}::{0} using 2:xtic(1) lc rgb "#F01010", "" every ::1:{0}::{0} using 3 lc rgb "#FFA500", \\'.format(i + 1)

        else:
            gnuScript = textwrap.dedent("""
                set title "Daily Load for {0:d} {1:s} Webapp Nodes"

                set xlabel "Date"
                set ylabel "Pageviews per Day"

                set nokey

                set grid ytics
                set xtics nomirror rotate by -45 scale 0 font ",8"

                set style data histogram
                set style histogram rows
                set boxwidth 0.8

                set style fill solid border -1

                plot "{2:s}" every ::1:1 using 2:xtic(1) lc rgb "#F01010" title "User Views", "" every ::1:1 using 3 lc rgb "#FFA500" title "API Views"\\
            """).format(len(nodeIDs), environment, dataFilePath + ".dat").strip()

            print >>gnuFileHandle, gnuScript

    return dataFilePath + ".gnu"

def getAccessLogs(accessLogDirs, startDate, stopDate, filterLogs):
    # Find the access logs
    logFileFormat = re.compile('^jive-httpd(?:-ssl)?-access\.log.*')
    allAccessLogPaths = []

    for logDir in accessLogDirs:
        if not os.path.isdir(logDir):
            logger.error("'%s' is not a directory", logDir)
            continue
        allAccessLogPaths.extend([os.path.join(logDir, f) for f in os.listdir(logDir) if logFileFormat.match(f)])

    accessLogPaths = []
    if allAccessLogPaths:
        logger.info("%d log files found", len(allAccessLogPaths))
        for l in allAccessLogPaths:
            logger.info("Found %s", l)

        if filterLogs:
            accessLogPaths = filterAccessLogs(allAccessLogPaths, startDate, stopDate)

            if not accessLogPaths:
                errorMsg = "No qualifying httpd access log files found in %s. If a valid log directory was provided try adjusting the time frame or disable log file name filtering."
                logger.error(errorMsg, ", ".join(accessLogDirs));
                exit(5)
        else:
            accessLogPaths = allAccessLogPaths

    return accessLogPaths

def shouldRecalculate(options, infoFilePath, dataFilePath, accessLogPaths):
    if accessLogPaths:
        maxMTime = max([os.path.getmtime(f) for f in accessLogPaths])
    else:
        maxMTime = 0

    info = {}
    if os.path.isfile(infoFilePath): 
        with open (infoFilePath, "r") as infoFileHandle:
            info = json.load(infoFileHandle)

    return options.force or not options.ignore and (isDataStale(infoFilePath, dataFilePath, maxMTime) or not optionsMatch(options, info))

def processLogFiles(accessLogPaths, startDate, stopDate, pathRE, agent):
    workerCount = max(min(multiprocessing.cpu_count() - 1, len(accessLogPaths)), 1)

    # Start multiprocessing
    logger.info("Spawning %d log readers for %d access log files", workerCount, len(accessLogPaths))
    multiprocessing.Process(target = spawnProcessors, args = (accessLogPaths, workerCount)).start()

    return transactionGenerator(len(accessLogPaths), startDate, stopDate, pathRE, agent)

def spawnProcessors (accessLogPaths, processLimit):
    for accessLogPath in accessLogPaths:
        accessLogPathQueue.put(accessLogPath)

    workers = [multiprocessing.Process(target = logFileProcessor) for i in range(processLimit)]

    for w in workers:
        w.start()
    
    for w in workers:
        w.join()

    logFilesProcessed.value = True

def transactionGenerator(logFileCount, startDate, stopDate, pathRE, agent):
    start = datetime.datetime.now()
    blockStart = datetime.datetime.now()
    blockLines = 0
    totalLines = 0
    passedCount = 0
    failedToParseCount = 0
    failedDateRangeCount = 0
    while not transactionQueue.empty() or not logFilesProcessed.value:
        try:
            transaction = transactionQueue.get(timeout=2)

            totalLines += 1
            blockLines += 1
            if totalLines % 100000 == 0:
                logger.info("%s httpd access log entries read (%s per second)", "{:,}".format(totalLines), "{:,}".format(int(blockLines / (datetime.datetime.now() - blockStart).total_seconds())))
                blockStart = datetime.datetime.now()
                blockLines = 0

            if not transaction.isValid():
                logger.warn("Skipping log entry because it cannot be parsed:\n\t%s", transaction.getRaw())
                failedToParseCount += 1
                continue

            if pathRE and not pathRE.match(transaction.path):
                logger.debug("Skipping log entry because the path doesn't match the specified pattern:\n\t%s", transaction.getRaw())
                continue

            if agent and not transaction.userAgent == agent:
                logger.debug("Skipping log entry because the user agent does not match that provided:\n\t%s", transaction.getRaw())
                continue

            if (startDate and transaction.date < startDate) or (stopDate and transaction.date >= stopDate):
                logger.debug("Skipping log entry because it is not in the specificed date range:\n\t%s", transaction.getRaw())
                failedDateRangeCount += 1
                continue

            passedCount += 1
            yield transaction
        except Queue.Empty:
            logger.warn("The transaction queue is empty. Probably just a timing issue; will test for the end condition again.")

    skippedCount = totalLines - passedCount
    logger.info("Processed %s transactions; skipped %s (%.2f%%).", "{:,}".format(totalLines), "{:,}".format(skippedCount), 100. * skippedCount / totalLines)
    if skippedCount > 0:
        logger.info("Of the transactions skipped, %.2f%% were outside the date range, and %.2f%% could not be parsed.", 100. * failedDateRangeCount / skippedCount, 100. * failedToParseCount / skippedCount)

def getStats(transactionGenerator):
    stats = {}
    for transaction in transactionGenerator:
        if not transaction.getNode() in stats:
            stats[transaction.getNode()] = Stats()

        nodeStats = stats[transaction.getNode()];
        nodeStats.agg(transaction)

    logger.info("Aggregating stats")
    aggStats = Stats()
    for node in stats:
        aggStats.aggNode(node, stats[node])

    return aggStats

def logFileProcessor():
    while not accessLogPathQueue.empty():
        try:
            accessLogPath = accessLogPathQueue.get(False)  

            logger.info("Processing %s", accessLogPath)

            for line in logFile(accessLogPath):
                transactionQueue.put(Transaction(line.rstrip(), os.path.dirname(accessLogPath)))

            logger.info("Finished processing %s", accessLogPath)
        except Queue.Empty:
            logger.warn("The access log queue is empty. Probably just a timing issue.")

    transactionQueue.close()
    transactionQueue.join_thread()

def writePlotInfo(options, minutes, startDate, stopDate, infoFilePath):
    # Calculate additional plot data
    transactionTotal = 0
    userviewTotal = 0
    apiTransactionTotal = 0
    authErrorTotal = 0
    servErrorTotal = 0
    for m in minutes:
        transactionTotal += m.getTransactionCount()
        userviewTotal += m.getUserviewCount()
        apiTransactionTotal += m.getAPITransactionCount()
        authErrorTotal += m.getAuthErrorCount()
        servErrorTotal += m.getServErrorCount()

    info = {
        'environment': options.environment,
        'host': options.host,
        'transactionTotal': transactionTotal,
        'apiTransactionTotal': apiTransactionTotal,
        'userviewTotal': userviewTotal,
        'pageviewTotal': userviewTotal + apiTransactionTotal / 6,
        'authErrors': authErrorTotal,
        'authErrorPct': authErrorTotal / float(transactionTotal) * 100,
        'serverErrors': servErrorTotal,
        'serverErrorPct': servErrorTotal / float(transactionTotal) * 100,
        'startDate': startDate.strftime(dateFormat),
        'stopDate': stopDate.strftime(dateFormat),
        'optionDgst': getOptionDigest(options)
    }

    with open (infoFilePath, "w") as infoFileHandle:
        json.dump(info, infoFileHandle, indent=4, separators=(",", ": "))

def printStats(stats):
    peakHour = stats.getPeakHours(1)[0]
    peakDay = stats.getPeakDays(1)[0]
    print "Peak hour: %s - %s" % (peakHour.getDate().strftime("%d/%b/%Y:%H:00"), locale.format("%d", peakHour.getPageviewCount(), grouping=True))
    print "Peak day: %s - %s" % (peakDay.getDate().strftime("%d/%b/%Y"), locale.format("%d", peakDay.getPageviewCount(), grouping=True))

def printPlotInfo(plotInfo):
    print "Total transactions: %s" % locale.format("%d", plotInfo['transactionTotal'], grouping=True)
    print "Total pageviews: %s" % locale.format("%d", plotInfo['pageviewTotal'], grouping=True)
    print "Total API transactions: %s" % locale.format("%d", plotInfo['apiTransactionTotal'], grouping=True)
    print "Total 50x errors: %s" % locale.format("%d", plotInfo['serverErrors'], grouping=True)
    print "Total 40x errors: %s" % locale.format("%d", plotInfo['authErrors'], grouping=True)

def plotPageviews(plotInfo, options, dataFilePath):
    plots = """
        set title "{info[environment]} - {info[host]}"
        set key inside right top

        set xlabel "Time"
        set ylabel "Pageviews per {extra[scale]}"
        set y2label "Seconds"

        set label "Date range: {info[startDate]} - {info[stopDate]}" at graph 0, graph 1 left offset character 2, character -1 front
        set label "Number of pageviews: {info[pageviewTotal]:,}" at graph 0, graph 1 left offset character 2, character -2 front
        set label "Number of transactions: {info[transactionTotal]:,}" at graph 0, graph 1 left offset character 2, character -3 front
        set label "50x errors: {info[serverErrors]:,} ({info[serverErrorPct]:.2f}%)" at graph 0, graph 1 left offset character 2, character -4 front
        set label "40x errors: {info[authErrors]:,} ({info[authErrorPct]:.2f}%)" at graph 0, graph 1 left offset character 2, character -5 front

        set autoscale xfix
        set grid ytics
        set xdata time
        set timefmt "%s"
        set xtics format "%H:%M" nomirror

        set yrange [0:*]

        set ytics nomirror
        set y2tics

        plot "{extra[dataFile]}" every ::1 using 1:($2+$3) title "APIviews" with boxes fs solid lc rgb "#FFA500",\
             "" every ::1 using 1:2 title "Userviews" with boxes fs solid lc rgb "#F01010"\
    """

    plotContext = {'info': plotInfo
        , 'extra': {'dataFile': dataFilePath
            , 'scale': "hour" if options.hourly else "minute"}
    }

    extraPlots = {}
    extraPlotContexts = {}
    if options.percentile:
        extraPlots['percentile'] = '"" every ::1 using 1:{percentile[columnNo]} title "{percentile[title]}" axes x1y2 with filledcurves y2=0 fs transparent solid 0.4 noborder'
        extraPlotContexts['percentile'] = {'columnNo': 7 if options.apitime else 6
            , 'title': "95% APIview Time" if options.apitime else "95% Userview Time"}

    extraPlots['avg'] = '"" every ::1 using 1:{avg[columnNo]} title "{avg[title]}" axes x1y2 with lines lc rgb "#104aa8" lw 2'
    extraPlotContexts['avg'] = {'columnNo': 5 if options.apitime else 4
        , 'title': "Avg. APIview Time" if options.apitime else "Avg. Userview Time"}

    for p in extraPlots:
        plots += ", " + extraPlots[p]
        plotContext[p] = extraPlotContexts[p]

    proc = subprocess.Popen(["gnuplot", "-p"], stdin=subprocess.PIPE)

    print >>proc.stdin, plots.format(**plotContext)

def setLoggingLevel(loggingLevel):
    loggingHandler = logging.StreamHandler()
    loggingFormatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s - %(message)s')
    loggingHandler.setFormatter(loggingFormatter)

    for loggerName in ["main", "tree"]:
        logger = logging.getLogger(loggerName)
        logger.setLevel(loggingLevel)
        logger.addHandler(loggingHandler)

def validateOptions(workDir, startDate, stopDate, usage):
    errorMsgs = []

    if not workDir:
        errorMsgs.append(usage.rstrip())
    elif not os.path.isdir(workDir):
        errorMsgs.append("The specified working directory, '%s', must exist." % workDir)

    if startDate and stopDate:
        if not startDate < stopDate:
            errorMsgs.append("The start date must be earlier than the stop date.")

    return errorMsgs

if __name__ == "__main__":
    main()
