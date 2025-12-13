class VideoStream:
	def __init__(self, filename):
		self.filename = filename
		try:
			self.file = open(filename, 'rb')
		except OSError:
			raise IOError

		self.frameNum = 0
		self.totalBytesRead = 0
		self.lastFrameSize = 0
		self.format = self._detectFormat()

	def _detectFormat(self):
		"""
		Auto-detect video format.

		Supports:
		- Custom format: 5-byte decimal length prefix
		- Standard MJPEG: JPEG markers (FF D8 ... FF D9)
		"""
		pos = self.file.tell()
		firstBytes = self.file.read(5)
		self.file.seek(pos)  # Reset position

		if not firstBytes or len(firstBytes) < 5:
			return 'unknown'

		# Try custom format (5-digit length)
		try:
			length = int(firstBytes)
			if 0 < length < 10000000:  # 10MB max
				return 'custom'
		except ValueError:
			pass

		# Check JPEG marker
		if firstBytes[0] == 0xFF and firstBytes[1] == 0xD8:
			return 'mjpeg'

		return 'custom'  # Default

	def _nextFrameCustom(self):
		data = self.file.read(5)
		if not data or len(data) < 5:
			return None

		try:
			framelength = int(data)
		except ValueError:
			return None

		frameData = self.file.read(framelength)
		if not frameData:
			return None

		self.frameNum += 1
		self.lastFrameSize = len(frameData)
		self.totalBytesRead += len(frameData)
		return frameData

	def _nextFrameMJPEG(self):
		"""
		Read frame from standard MJPEG file.

		JPEG structure:
		- Start: FF D8 (SOI - Start of Image)
		- End: FF D9 (EOI - End of Image)
		"""
		# Find start marker
		while True:
			byte = self.file.read(1)
			if not byte:
				return None
			if byte == b'\xff':
				nextByte = self.file.read(1)
				if not nextByte:
					return None
				if nextByte == b'\xd8':  # SOI
					frameData = b'\xff\xd8'
					break

		# Read until end marker
		while True:
			byte = self.file.read(1)
			if not byte:
				break
			frameData += byte

			if byte == b'\xff':
				nextByte = self.file.read(1)
				if not nextByte:
					break
				frameData += nextByte
				if nextByte == b'\xd9':  # EOI
					break

			# Safety check
			if len(frameData) > 10000000:  # 10MB
				print("[VideoStream] Frame too large, skipping")
				return None

		self.frameNum += 1
		self.lastFrameSize = len(frameData)
		self.totalBytesRead += len(frameData)

		# Log large frames
		if len(frameData) > 500000:  # ~500KB (4K)
			print(f"[VideoStream] 4K Frame {self.frameNum}: {len(frameData)/1024.1:.1f} KB")
		elif len(frameData) > 100000:  # ~100KB (HD)
			print(f"[VideoStream] HD Frame {self.frameNum}: {len(frameData)/1024.1:.1f} KB")

		return frameData

	def nextFrame(self):
		"""Get next frame."""
		if self.format == 'mjpeg':
			return self._nextFrameMJPEG()
		return self._nextFrameCustom()

	def frameNbr(self):
		"""Get frame number."""
		return self.frameNum

	def getLastFrameSize(self):
		"""Get the size of the last frame read."""
		return self.lastFrameSize

	def getTotalBytesRead(self):
		"""Get total bytes read from the video file."""
		return self.totalBytesRead

	def reset(self):
		"""Reset the video stream to the beginning."""
		self.file.seek(0)
		self.frameNum = 0
		self.totalBytesRead = 0
		self.lastFrameSize = 0
