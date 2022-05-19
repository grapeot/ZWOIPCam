import numpy as np
from math import log2, pow

class AutoExposurer:
    def __init__(self, maxGain, maxExp):
        self.maxGain = maxGain
        self.maxExp = maxExp
        self.skipFrames = 5  # the first skipFrames frames will be skipped
        self.gainStep = 50 if maxGain > 400 else 10
        self.targetBrightnessLow = 100
        self.targetBrightnessHigh = 160
        self.targetBrightness = (self.targetBrightnessHigh + self.targetBrightnessLow) / 2

    # Returns (changed, newGain, newExp, med)
    def adjustExp(self, gain, exp, img):
        if self.skipFrames > 0:
            self.skipFrames -= 1
            return (False, None, None, 100)
        med = np.median(img)
        if self.targetBrightnessLow < med < self.targetBrightnessHigh:
            return (False, None, None, med)
        if med > self.targetBrightnessHigh:
            ratio = med / self.targetBrightness # > 1.0
            # Need to reduce exposure. Reduce gain if possible.
            gainDelta = self.gainStep * log2(ratio)
            if exp >= gainDelta:
                return (True, int(gain - gainDelta), int(exp), med)
            gainDeltaFulfilled = pow(2, gain)
            exposureDelta = ratio / gainDeltaFulfilled
            # We don't have a min epxosure
            return (True, 0, int(exp / exposureDelta), med)
        if med < self.targetBrightnessLow:
            ratio = self.targetBrightness / med
            # Need to bump exposure. Increase exposure if possible
            if exp * ratio < self.maxExp:
                return (True, gain, int(exp * ratio), med)
            expDeltaFulfilled = self.maxExp / exp
            gainDelta = self.gainStep * log2(ratio / expDeltaFulfilled)
            newGain = min(self.maxGain, gainDelta + gain)
            return (True, int(newGain), int(self.maxExp), med)

