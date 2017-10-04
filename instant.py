#!/usr/bin/python
import math

from transaction import Transaction

class Instant:

    def __init__(self, date):
        self.date = date
        self.transactionCount = 0
        self.userviewCount = 0
        self.asyncviewCount = 0
        self.authErrorCount = 0
        self.servErrorCount = 0
        self.bytes = 0
        self.userviewTime = 0
        self.userviewTimes = []
        self.asyncviewTime = 0
        self.asyncviewTimes = []

    def getDate(self):
        return self.date

    def update(self, transaction):
        self.transactionCount += 1

        if transaction.isAuthError():
            self.authErrorCount += 1
        elif transaction.isServerError():
            self.servErrorCount += 1
        elif transaction.isUserview():
            self.userviewCount += 1
            self.userviewTime += transaction.time
            self.userviewTimes.append(transaction.time)
        elif transaction.isAsyncview():
            self.asyncviewCount += 1
            self.asyncviewTime += transaction.time
            self.asyncviewTimes.append(transaction.time)

    def merge(self, other):
        self.transactionCount += other.transactionCount
        self.authErrorCount += other.authErrorCount
        self.servErrorCount += other.servErrorCount
        self.userviewCount += other.userviewCount
        self.asyncviewCount += other.asyncviewCount
        self.userviewTime += other.userviewTime
        self.userviewTimes += other.userviewTimes
        self.asyncviewTime += other.asyncviewTime
        self.asyncviewTimes += other.asyncviewTimes

    def getTransactionCount(self):
        return self.transactionCount

    def getUserviewCount(self):
        return self.userviewCount

    def getAPITransactionCount(self):
        return self.asyncviewCount

    def getApiviewCount(self):
        return self.asyncviewCount / 6

    def getPageviewCount(self):
        return self.userviewCount + self.getApiviewCount()

    def getAuthErrorCount(self):
        return self.authErrorCount

    def getServErrorCount(self):
        return self.servErrorCount

    def getKilobytes(self):
        return self.bytes / 1024

    def getUserviewAvgTime(self):
        return float(self.userviewTime) / self.userviewCount if self.userviewCount else 0

    def getAsyncviewAvgTime(self):
        return float(self.asyncviewTime) / self.asyncviewCount if self.asyncviewCount else 0

    def get95PercentileUserviewTime(self):
        if not self.userviewTimes:
            return 0
        self.userviewTimes.sort()
        return self.userviewTimes[int(len(self.userviewTimes) * .95)]

    def get95PercentileAsyncviewTime(self):
        if not self.asyncviewTimes:
            return 0
        self.asyncviewTimes.sort()
        return self.asyncviewTimes[int(len(self.asyncviewTimes) * .95)]

    def get90PercentileUserviewTime(self):
        self.userviewTimes.sort()
        return self.userviewTimes[int(len(self.userviewTimes) * .9)]

    def get90PercentileAsyncviewTime(self):
        self.asyncviewTimes.sort()
        return self.asyncviewTimes[int(len(self.asyncviewTimes) * .9)]

    def getStdDevUserviewTime(self):
        if self.userviewCount > 0:
            mean = self.getUserviewAvgTime()
            return math.sqrt(reduce(lambda x, y: x + y, [(x - mean)**2 for x in self.userviewTimes]) / self.userviewCount)
        else:
            return 0

    def getStdDevUserviewTime(self):
        if self.userviewCount > 0:
            mean = self.getUserviewAvgTime()
            return math.sqrt(reduce(lambda x, y: x + y, [(x - mean)**2 for x in self.userviewTimes]) / self.userviewCount)
        else:
            return 0
