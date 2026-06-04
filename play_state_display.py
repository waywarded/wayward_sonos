import pygame
import random

def moveToward(current: float, target: float, maxMove: float) -> float:
	if abs(target - current) <= maxMove:
		return target
	
	return current + maxMove * (1 if target > current else -1)

class PlayStateSpectrumBar:
	def __init__(self, parent : PlayStateDisplay):
		self.curHeight = 0
		self.targetHeight = 0
		self.inactiveTargetHeight = 0
		self.scaleRate = 50
		self.parent = parent
		self.dir = 1

	def update(self, deltaTime, isActive):
		if not isActive:
			self.targetHeight = 0
		elif self.curHeight == self.targetHeight:
				self.chooseNewTargetHeight()

		# move value toward target height without overshoot
		moveAmt = deltaTime * self.scaleRate
		self.curHeight = moveToward(self.curHeight, self.targetHeight, moveAmt)

	def chooseNewTargetHeight(self):
		if (self.targetHeight != self.parent.barHeightMin):
			self.targetHeight = random.uniform(self.parent.barHeightMin, self.parent.barHeightMax)
		else:
			self.targetHeight = self.parent.barHeightMin

class PlayStateDisplay:
	def __init__(self, display):
		self.display = display
		self.barCount = 6
		self.barHeightMax = 25
		self.barHeightMin = 5
		self.barWidth = 4
		self.barGap = 5
		self.bars = [
			PlayStateSpectrumBar(self)
			for _ in range(self.barCount)
		]


		# self.barSurface = pygame.Surface((self.barWidth,self.barHeightMax))
		# self.barSurface.fill((128,128,128))
		gradImage = pygame.image.load('assets/barGradient.png').convert()
		self.barSurface = pygame.transform.scale(gradImage, (self.barWidth, self.barHeightMax))

		self.totalWidth = self.barCount * (self.barWidth + self.barGap) - self.barGap

	def update(self, deltaTime, isActive):
		for bar in self.bars:
			bar.update(deltaTime, isActive)
	
	def render(self, screen, centerX, centerY):
		startX = centerX - self.totalWidth // 2
		halfFullBarH = self.barHeightMax // 2
		for i, bar in enumerate(self.bars):
			barH = max(0,bar.curHeight)
			if (barH < 1):
				continue
			x = startX + i * (self.barWidth + self.barGap)
			halfBarH = barH//2
			r = pygame.Rect(0,halfFullBarH - halfBarH, self.barWidth, barH)
			screen.blit(self.barSurface, (x, centerY - halfBarH), r)