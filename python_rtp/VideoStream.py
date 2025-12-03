class VideoStream:
	def __init__(self, filename):
		self.filename = filename
		try:
			self.file = open(filename, 'rb')
		except:
			raise IOError
		self.frameNum = 0
		self.buffer = b''

	def nextFrame(self):
		"""Get next JPEG frame delimited by SOI (0xFFD8) and EOI (0xFFD9)."""
		SOI = b'\xff\xd8'
		EOI = b'\xff\xd9'

		while True:
			soi = self.buffer.find(SOI)
			if (soi != -1):
				eoi = self.buffer.find(EOI, soi + 2)
				if (eoi != -1):
					frame = self.buffer[soi:eoi + 2]
					self.buffer = self.buffer[eoi + 2:]
					self.frameNum += 1
					return frame
		
			chunk = self.file.read(4096)
			if not chunk:
				return None
			self.buffer += chunk
		# data = self.file.read(5) # Get the framelength from the first 5 bits
		# if data: 
		# 	framelength = int(data)
							
		# 	# Read the current frame
		# 	data = self.file.read(framelength)
		# 	self.frameNum += 1
		# return data
		
	def frameNbr(self):
		"""Get frame number."""
		return self.frameNum
	
	