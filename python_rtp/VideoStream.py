class VideoStream:
	def __init__(self, filename):
		self.filename = filename
		try:
			self.file = open(filename, 'rb')
		except:
			raise IOError
		self.frameNum = 0
		
	def nextFrame(self):
		"""Get next frame."""
		data = b''
		# Find SOI (\xff\xd8) 
		while True:
			byte = self.file.read(1)
			if not byte: return None
			if byte == b'\xff':
				nextByte = self.file.read(1)
				if not nextByte:
					return None
				if nextByte == b'\xd8': 
					data = b'\xff\xd8'
					break
		
		#  Find EOI (\xff\xd9)
		while True:
			byte = self.file.read(1)
			if not byte: return None
			data+=byte
			if len(data)>=2 and data[-2:] == b'\xff\xd9':
				self.frameNum += 1
				return data
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
	
	