#!/usr/bin/python
import datetime

from instant import Instant

class Stats:

    def __init__(self):
        self.minutes = {}
        self.hours = {}
        self.days = {}
        self.nodes = {}

    def agg(self, transaction):
        # Get keys
        minute = datetime.datetime(transaction.date.year, transaction.date.month, transaction.date.day, transaction.date.hour, transaction.date.minute)
        hour = datetime.datetime(transaction.date.year, transaction.date.month, transaction.date.day, transaction.date.hour)
        day = Stats.getStartDate(transaction.date, datetime.timedelta(1))

        # Update stats
        if not minute in self.minutes:
            self.minutes[minute] = Instant(minute)
        instant = self.minutes[minute]
        instant.update(transaction)

        if not hour in self.hours:
            self.hours[hour] = Instant(hour)
        instant = self.hours[hour]
        instant.update(transaction)

        if not day in self.days:
            self.days[day] = Instant(day)
        instant = self.days[day]
        instant.update(transaction)

    def aggNode(self, node, stats):
        if not node in self.nodes:
            for minute in stats.getAllMinutes():
                self.aggMinute(minute)

            self.nodes[node] = stats

    def aggMinute(self, minute):
        # Get keys
        minuteKey = minute.getDate()
        hourKey = datetime.datetime(minute.getDate().year, minute.getDate().month, minute.getDate().day, minute.getDate().hour)
        dayKey = datetime.datetime(minute.getDate().year, minute.getDate().month, minute.getDate().day)

        # Update stats
        if not minuteKey in self.minutes:
            self.minutes[minuteKey] = Instant(minuteKey)
        instant = self.minutes[minuteKey]
        instant.merge(minute)

        if not hourKey in self.hours:
            self.hours[hourKey] = Instant(hourKey)
        instant = self.hours[hourKey]
        instant.merge(minute)

        if not dayKey in self.days:
            self.days[dayKey] = Instant(dayKey)
        instant = self.days[dayKey]
        instant.merge(minute)

    def getNode(self, node):
        return self.nodes[node]

    def getAllNodes(self):
        return self.nodes

    def getPeakHour(self):
        return max(self.hours.values(), key=lambda x: x.getPageviewCount()).getDate()

    def getPeakDay(self):
        return max(self.days.values(), key=lambda x: x.getPageviewCount()).getDate()

    def getPeakHours(self, count):
        peakHour = self.getPeakHour()
        minHour = peakHour - datetime.timedelta(hours=count / 2)
        maxHour = peakHour + datetime.timedelta(hours=(count + 1) / 2)

        return self.getHours(minHour, maxHour)

    def getHours(self, startDateTime, stopDateTime):
        selectHours = []

        startHour = Stats.getStartDate(startDateTime, datetime.timedelta(hours=1)) if startDateTime else None
        stopHour = Stats.getStopDate(stopDateTime, datetime.timedelta(hours=1)) if stopDateTime else None

        for hour in self.hours.values():
            if (not startHour or hour.getDate() >= startHour) and (not stopHour or hour.getDate() < stopHour):
                    selectHours.append(hour)

        selectHours.sort(key=lambda x: x.getDate())
        return selectHours

    def getPeakDays(self, count):
        peakDay = self.getPeakDay()
        minDay = peakDay - datetime.timedelta(days=count / 2)
        maxDay = peakDay + datetime.timedelta(days=(count + 1) / 2)

        return self.getDays(minDay, maxDay)

    def getDays(self, startDateTime, stopDateTime):
        selectDays = []

        startDay = Stats.getStartDate(startDateTime, datetime.timedelta(1)) if startDateTime else None
        stopDay = Stats.getStopDate(stopDateTime, datetime.timedelta(1)) if stopDateTime else None

        for day in self.days.values():
            if (not startDay or day.getDate() >= startDay) and (not stopDay or day.getDate() < stopDay):
                selectDays.append(day)

        selectDays.sort(key=lambda x: x.getDate())
        return selectDays

    def getMinutes(self, startDate, stopDate):
        selectMinutes = []

        for minute in self.minutes.values():
            if minute.getDate() >= startDate and minute.getDate() < stopDate:
                    selectMinutes.append(minute)

        selectMinutes.sort(key=lambda x: x.getDate())
        return selectMinutes

    def getAllMinutes(self):
        return self.minutes.values()

    def isEmpty(self):
        return not self.minutes

    @staticmethod
    def getStartDate(dt, resolution):
        if resolution == datetime.timedelta(1):
            return datetime.datetime(dt.year, dt.month, dt.day)
        elif resolution == datetime.timedelta(hours=1):
            return datetime.datetime(dt.year, dt.month, dt.day, dt.hour)
        else:
            return dt

    @staticmethod
    def getStopDate(dt, resolution):
        startDate = Stats.getStartDate(dt, resolution)
        if dt > startDate:
            return startDate + resolution
        else:
            return startDate
