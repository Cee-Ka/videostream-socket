from tkinter import * # type: ignore
import tkinter.messagebox as tkMessageBox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os
import queue
from RtpPacket import RtpPacket
import time
CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class Client:
	INIT = 0
	READY = 1
	PLAYING = 2
	state = INIT
	
	SETUP = 0
	PLAY = 1
	PAUSE = 2
	TEARDOWN = 3
	
	# Initiation..
	def __init__(self, master, serveraddr, serverport, rtpport, filename):
		self.master = master
		self.master.protocol("WM_DELETE_WINDOW", self.handler)
		self.createWidgets()
		self.serverAddr = serveraddr
		self.serverPort = int(serverport)
		self.rtpPort = int(rtpport)
		self.fileName = filename
		self.rtspSeq = 0
		self.sessionId = 0
		self.requestSent = -1
		self.teardownAcked = 0
		self.connectToServer()
		self.frameNbr = 0

		self.totalBytesReceived = 0 # Tổng số byte đã nhận
		self.startTime = 0          # Thời gian bắt đầu nhận gói đầu tiên
		self.endTime = 0            # Thời gian kết thúc
		self.totalFramesReceived = 0 # Tổng số frame hoàn chỉnh đã nhận

		self.frameBuffer = queue.Queue(maxsize=100)
		self.incompleteFrame = b''
		self.bufferStarted = False

	def resetVideo(self):
		"""Hàm dọn dẹp bộ nhớ để chuẩn bị cho lần Reload tiếp theo"""
		self.frameNbr = 0
		self.incompleteFrame = b''
		self.bufferStarted = False
		
		# Xóa sạch hàng đợi (Queue)
		with self.frameBuffer.mutex:
			self.frameBuffer.queue.clear()
			
		# Reset các biến thống kê (Analysis)
		self.totalBytesReceived = 0
		self.startTime = 0
		self.endTime = 0
		self.totalFramesReceived = 0

		# Xóa file cache trên ổ cứng
		try:
			os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT)
		except OSError:
			pass	

	def createWidgets(self):
		"""Build GUI."""
		self.master.grid_rowconfigure(0, weight=1)
		self.master.grid_columnconfigure(0, weight=1)
		# Create Setup button
		self.setup = Button(self.master, width=20, padx=3, pady=3)
		self.setup["text"] = "Setup"
		self.setup["command"] = self.setupMovie
		self.setup.grid(row=1, column=0, padx=2, pady=2)
		
		# Create Play button		
		self.start = Button(self.master, width=20, padx=3, pady=3)
		self.start["text"] = "Play"
		self.start["command"] = self.playMovie
		self.start.grid(row=1, column=1, padx=2, pady=2)
		
		# Create Pause button			
		self.pause = Button(self.master, width=20, padx=3, pady=3)
		self.pause["text"] = "Pause"
		self.pause["command"] = self.pauseMovie
		self.pause.grid(row=1, column=2, padx=2, pady=2)
		
		# Create Teardown button
		self.teardown = Button(self.master, width=20, padx=3, pady=3)
		self.teardown["text"] = "Teardown"
		self.teardown["command"] =  self.exitClient
		self.teardown.grid(row=1, column=3, padx=2, pady=2)
		
		# Create a label to display the movie
		self.label = Label(self.master)
		self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 
	
	def setupMovie(self):
		"""Setup button handler."""
		if self.state == self.INIT:
			self.sendRtspRequest(self.SETUP)
	
	def exitClient(self):
		"""Teardown button handler."""
		self.playEvent.set()
		self.sendRtspRequest(self.TEARDOWN)
		
		# --- ANALYSIS REPORT (BÁO CÁO PHÂN TÍCH) ---
		print("\n" + "="*40)
		print("       VIDEO STREAMING SESSION REPORT       ")
		print("="*40)
		
		# 1. Tính thời gian session
		duration = self.endTime - self.startTime
		if duration <= 0: duration = 1 # Tránh chia cho 0
		
		# 2. Tính Frame Loss (Tỉ lệ mất frame)
		# Server gửi frame sequence: 1, 2, 3... N
		# Nếu self.frameNbr (số lớn nhất nhận được) là 100, mà totalFramesReceived chỉ là 95
		# -> Mất 5 frame.
		expectedFrames = self.frameNbr
		if expectedFrames > 0:
			lostFrames = expectedFrames - self.totalFramesReceived
			lossRate = (lostFrames / expectedFrames) * 100
		else:
			lostFrames = 0
			lossRate = 0.0
			
		# 3. Tính Network Usage (Băng thông)
		# Chuyển đổi Bytes -> kBits (Kilobits)
		totalKbits = (self.totalBytesReceived * 8) / 1000
		bitrate = totalKbits / duration # kbps
		
		print(f"Total Duration      : {duration:.2f} seconds")
		print(f"Total Bytes Received: {self.totalBytesReceived / 1024:.2f} KB")
		print(f"Average Bitrate     : {bitrate:.2f} kbps")
		print("-" * 40)
		print(f"Max Sequence Number : {expectedFrames}")
		print(f"Total Frames Decoded: {self.totalFramesReceived}")
		print(f"Frames Lost         : {lostFrames}")
		print(f"Packet Loss Rate    : {lossRate:.2f} %")
		print("="*40 + "\n")
		# -------------------------------------------

		self.master.destroy() 
		try:
			os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT) 
		except:
			pass

	def pauseMovie(self):
		"""Pause button handler."""
		if self.state == self.PLAYING:
			self.sendRtspRequest(self.PAUSE)
	
	def playMovie(self):
		"""Play button handler."""
		if self.state == self.READY:
			# Create a new thread to listen for RTP packets
			self.playEvent = threading.Event()
			self.playEvent.clear()

			# Thread 1: Nhận dữ liệu mạng và đẩy vào Buffer
			threading.Thread(target=self.listenRtp).start()
			self.maxedFrameRecieved=self.frameNbr
			# print(self.maxedFrameRecieved)
			# Thread 2: Lấy từ Buffer ra hiển thị (Advanced)
			threading.Thread(target=self.consumeBuffer).start()
			self.sendRtspRequest(self.PLAY)
	
	def listenRtp(self):		
		"""Listen for RTP packets."""
		while True:
			try:
				data = self.rtpSocket.recv(20480)
				if data:
					# --- ANALYSIS: Cập nhật dữ liệu ---
					curTime = time.time()
					if self.startTime == 0:
						self.startTime = curTime # Ghi lại mốc thời gian bắt đầu
					self.endTime = curTime       # Cập nhật thời gian mới nhất
					
					self.totalBytesReceived += len(data) # Cộng dồn dung lượng
					# ----------------------------------

					rtpPacket = RtpPacket()
					rtpPacket.decode(data)
					
					self.incompleteFrame += rtpPacket.getPayload()

					if rtpPacket.getMarker() == 1:
						# --- ANALYSIS: Đếm số frame nhận được ---
						self.totalFramesReceived += 1
						# ----------------------------------------
						
						currFrameNbr = rtpPacket.seqNum()
						# ... (Logic buffer cũ giữ nguyên)
						if currFrameNbr > self.frameNbr:
							self.frameNbr = currFrameNbr
							try:
								self.frameBuffer.put(self.incompleteFrame, timeout=1.0)
							except queue.Full:
								pass 
						self.incompleteFrame = b''
										
					# if currFrameNbr > self.frameNbr: # Discard the late packet
					# 	self.frameNbr = currFrameNbr
						# self.updateMovie(self.writeFrame(rtpPacket.getPayload()))
			except:
				# Stop listening upon requesting PAUSE or TEARDOWN
				if self.playEvent.isSet(): 
					break
				
				# Upon receiving ACK for TEARDOWN request,
				# close the RTP socket
				if self.teardownAcked == 1:
					self.rtpSocket.shutdown(socket.SHUT_RDWR)
					self.rtpSocket.close()
					break

	def consumeBuffer(self):
		"""Hàm mới: Lấy frame từ buffer và hiển thị (Client-side Caching)"""
		FRAME_DELAY = 0.05 # Tốc độ phát (50ms)
		PRE_BUFFER = 20    # Cần nạp trước 10 frame rồi mới chạy (Pre-buffering)

		while True:
			if self.playEvent.isSet():
				break

			# Logic Pre-buffering: Đợi buffer nạp đủ N frame rồi mới bắt đầu
			if not self.bufferStarted:
				if self.frameBuffer.qsize() >= PRE_BUFFER:
					self.bufferStarted = True
					print("Buffering complete. Starting playback...")
				else:
					# Đợi một chút để buffer đầy
					threading.Event().wait(0.1)
					continue

			# Logic Playback
			if not self.frameBuffer.empty():
				frameData = self.frameBuffer.get()
				
				# --- SỬA LỖI TẠI ĐÂY ---
				try:
					# Thử ghi file và hiển thị
					path = self.writeFrame(frameData)
					self.updateMovie(path)
				except Exception as e:
					# Nếu ảnh lỗi (do mất gói tin UDP), in ra lỗi và BỎ QUA frame này
					# Không để chương trình bị crash
					print(f"Skipping bad frame: {e}")
				# -----------------------

				# Giả lập tốc độ khung hình (sleep)
				threading.Event().wait(FRAME_DELAY)
			else:
				# Nếu buffer rỗng, đợi thêm dữ liệu
				threading.Event().wait(0.01)
	def writeFrame(self, data):
		"""Write the received frame to a temp image file. Return the image file."""
		cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
		file = open(cachename, "wb")
		file.write(data)
		file.close()
		
		return cachename
	
	def updateMovie(self, imageFile):
		"""Update the image file as video frame in the GUI."""
		photo = ImageTk.PhotoImage(Image.open(imageFile))
		self.label.configure(image = photo, anchor="center") 
		self.label.image = photo
		
	def connectToServer(self):
		"""Connect to the Server. Start a new RTSP/TCP session."""
		self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			self.rtspSocket.connect((self.serverAddr, self.serverPort))
		except:
			tkMessageBox.showwarning('Connection Failed', 'Connection to \'%s\' failed.' %self.serverAddr)
	
	def sendRtspRequest(self, requestCode):
		"""Send RTSP request to the server."""	
		#-------------
		# TO COMPLETE
		#-------------
		
		# Setup request
		if requestCode == self.SETUP and self.state == self.INIT:
			threading.Thread(target=self.recvRtspReply).start()
			# Update RTSP sequence number.
			self.rtspSeq += 1
			
			# Write the RTSP request to be sent.
			request = f"SETUP {self.fileName} RTSP/1.0\n" \
					  f"CSeq: {self.rtspSeq}\n" \
					  f"Transport: RTP/UDP; client_port= {self.rtpPort}\n"
			
			# Keep track of the sent request.
			self.requestSent = self.SETUP
		
		# Play 
		elif requestCode == self.PLAY and self.state == self.READY:
			# Update RTSP sequence number.
			self.rtspSeq += 1
			
			# Write the RTSP request to be sent.
			request = f"PLAY {self.fileName} RTSP/1.0\n" \
					  f"CSeq: {self.rtspSeq}\n" \
					  f"Session: {self.sessionId}"
			
			# Keep track of the sent request.
			self.requestSent = self.PLAY
		
		# Pause request
		elif requestCode == self.PAUSE and self.state == self.PLAYING:
			# Update RTSP sequence number.
			self.rtspSeq += 1
			
			# Write the RTSP request to be sent.
			request = f"PAUSE {self.fileName} RTSP/1.0\n" \
					  f"CSeq: {self.rtspSeq}\n" \
					  f"Session: {self.sessionId}"
			
			# Keep track of the sent request.
			self.requestSent = self.PAUSE
			
		# Teardown request
		elif requestCode == self.TEARDOWN and not self.state == self.INIT:
			# Update RTSP sequence number.
			self.rtspSeq += 1
			
			# Write the RTSP request to be sent.
			request = f"TEARDOWN {self.fileName} RTSP/1.0\n" \
					  f"Cseq: {self.rtspSeq}\n" \
					  f"Session: {self.sessionId}"
			
			# Keep track of the sent request.
			self.requestSent = self.TEARDOWN
		else:
			return
		
		# Send the RTSP request using rtspSocket.
		self.rtspSocket.send(request.encode("utf-8"))
		
		print('\nData sent:\n' + request)
	
	def recvRtspReply(self):
		"""Receive RTSP reply from the server."""
		while True:
			reply = self.rtspSocket.recv(1024)
			
			if reply: 
				self.parseRtspReply(reply.decode("utf-8"))
			
			# Close the RTSP socket upon requesting Teardown
			if self.requestSent == self.TEARDOWN:
				self.rtspSocket.shutdown(socket.SHUT_RDWR)
				self.rtspSocket.close()
				break
	
	def parseRtspReply(self, data):
		"""Parse the RTSP reply from the server."""
		lines = data.split('\n')
		seqNum = int(lines[1].split(' ')[1])
		
		# Process only if the server reply's sequence number is the same as the request's
		if seqNum == self.rtspSeq:
			session = int(lines[2].split(' ')[1])
			# New RTSP session ID
			if self.sessionId == 0:
				self.sessionId = session
			
			# Process only if the session ID is the same
			if self.sessionId == session:
				if int(lines[0].split(' ')[1]) == 200: 
					if self.requestSent == self.SETUP:
						#-------------
						# TO COMPLETE
						#-------------
						# Update RTSP state.
						self.state = self.READY
						
						# Open RTP port.
						self.openRtpPort() 
					elif self.requestSent == self.PLAY:
						self.state = self.PLAYING
					elif self.requestSent == self.PAUSE:
						self.state = self.READY
						
						# The play thread exits. A new thread is created on resume.
						self.playEvent.set()
					elif self.requestSent == self.TEARDOWN:
						self.state = self.INIT
						
						# Flag the teardownAcked to close the socket.
						self.teardownAcked = 1 
	
	def openRtpPort(self):
		"""Open RTP socket binded to a specified port."""
		#-------------
		# TO COMPLETE
		#-------------
		# Create a new datagram socket to receive RTP packets from the server
		self.rtpSocket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
		
		# Set the timeout value of the socket to 0.5sec
		self.rtpSocket.settimeout(0.5)
		
		try:
			# Bind the socket to the address using the RTP port given by the client user
			self.rtpSocket.bind(("", self.rtpPort))
		except:
			tkMessageBox.showwarning('Unable to Bind', 'Unable to bind PORT=%d' %self.rtpPort)

	def handler(self):
		"""Handler on explicitly closing the GUI window."""
		self.pauseMovie()
		if tkMessageBox.askokcancel("Quit?", "Are you sure you want to quit?"):
			self.exitClient()
		else: # When the user presses cancel, resume playing.
			self.playMovie()

