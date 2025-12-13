from random import randint
import sys, traceback, threading, socket

from VideoStream import VideoStream
from RtpPacket import RtpPacket

class ServerWorker:
	SETUP = 'SETUP'
	PLAY = 'PLAY'
	PAUSE = 'PAUSE'
	TEARDOWN = 'TEARDOWN'
	
	INIT = 0
	READY = 1
	PLAYING = 2
	state = INIT

	OK_200 = 0
	FILE_NOT_FOUND_404 = 1
	CON_ERR_500 = 2
	
	clientInfo = {}
	
	def __init__(self, clientInfo):
		self.clientInfo = clientInfo
		
	def run(self):
		threading.Thread(target=self.recvRtspRequest).start()
	
	def recvRtspRequest(self):
		"""Receive RTSP request from the client."""
		connSocket = self.clientInfo['rtspSocket'][0]
		while True:            
			data = connSocket.recv(256)
			if data:
				print("Data received:\n" + data.decode("utf-8"))
				self.processRtspRequest(data.decode("utf-8"))
	
	def processRtspRequest(self, data):
		"""Process RTSP request sent from the client."""
		# Get the request type
		request = data.split('\n')
		line1 = request[0].split(' ')
		requestType = line1[0]
		
		# Get the media file name
		filename = line1[1]
		
		# Get the RTSP sequence number 
		seq = request[1].split(' ')
		
		# Process SETUP request
		if requestType == self.SETUP:
			if self.state == self.INIT:
				# Update state
				print("processing SETUP\n")
				
				try:
					self.clientInfo['videoStream'] = VideoStream(filename)
					self.state = self.READY
				except IOError:
					self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
				
				# Generate a randomized RTSP session ID
				self.clientInfo['session'] = randint(100000, 999999)
				
				# Get the RTP/UDP port from the last line
				self.clientInfo['rtpPort'] = request[2].split(' ')[3]
				# --- ĐOẠN CODE MỚI: BẮT ĐẦU GỬI NGAY TẠI ĐÂY ---
                # 1. Tạo Socket RTP
				self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
				
                # 2. Tạo Event để quản lý dừng/chạy
				self.clientInfo['event'] = threading.Event()
                
                # # 3. Bắt đầu luồng gửi dữ liệu luôn
				# self.clientInfo['worker']= threading.Thread(target=self.sendRtp) 
				# self.clientInfo['worker'].start()
				
				# Send RTSP reply
				self.replyRtsp(self.OK_200, seq[1])

				
		# Process PLAY request 		
		elif requestType == self.PLAY:
			if self.state == self.READY:
				print("processing PLAY\n")
				self.state = self.PLAYING
				
				# --- LOGIC MỚI: KIỂM TRA VÀ KHỞI ĐỘNG LẠI LUỒNG GỬI ---
				# Kiểm tra xem luồng gửi có đang sống không?
				# Nếu chưa có 'worker' (lỗi logic) HOẶC luồng đã chết (do PAUSE trước đó) -> Tạo mới
				if 'worker' not in self.clientInfo or not self.clientInfo['worker'].is_alive():
					self.clientInfo['event'] = threading.Event()
					self.clientInfo['worker'] = threading.Thread(target=self.sendRtp) 
					self.clientInfo['worker'].start()
				
				# Create a new socket for RTP/UDP
				# self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
				
				self.replyRtsp(self.OK_200, seq[1])
				
				# # Create a new thread and start sending RTP packets
				# self.clientInfo['event'] = threading.Event()
				# self.clientInfo['worker']= threading.Thread(target=self.sendRtp) 
				# self.clientInfo['worker'].start()
		
		# Process PAUSE request
		elif requestType == self.PAUSE:
			if self.state == self.PLAYING:
				print("processing PAUSE\n")
				self.state = self.READY
				
				self.clientInfo['event'].set()
			
				self.replyRtsp(self.OK_200, seq[1])
		
		# Process TEARDOWN request
		elif requestType == self.TEARDOWN:
			print("processing TEARDOWN\n")

			self.clientInfo['event'].set()
			
			self.replyRtsp(self.OK_200, seq[1])
			
			# Close the RTP socket
			self.clientInfo['rtpSocket'].close()
			
	def sendRtp(self):
		"""Send RTP packets over UDP."""
		MAX_PAYLOAD_SIZE = 1400 # Kích thước an toàn cho UDP (MTU)
		preBufferCount = 0      # Đếm số frame đã gửi trong lúc chờ
		PRE_BUFFER_LIMIT = 20
		while True:
			self.clientInfo['event'].wait(0.05) 
			# Stop sending if request is PAUSE or TEARDOWN
			if self.clientInfo['event'].isSet(): 
				break 
				
			data = self.clientInfo['videoStream'].nextFrame()
			if data: 
				frameNumber = self.clientInfo['videoStream'].frameNbr()
				try:
					address = self.clientInfo['rtspSocket'][1][0]
					port = int(self.clientInfo['rtpPort'])

					data_len = len(data)
					curr_pos = 0

					while curr_pos < data_len:
						# Lấy 1 đoạn data (chunk)
						chunk = data[curr_pos : curr_pos + MAX_PAYLOAD_SIZE]
						curr_pos += MAX_PAYLOAD_SIZE
						
						# Nếu đã gửi hết data của frame này, marker = 1. Ngược lại = 0
						if curr_pos >= data_len:
							marker = 1
						else:
							marker = 0
						self.clientInfo['rtpSocket'].sendto(self.makeRtp(chunk, frameNumber, marker),(address,port))
				except:
					print("Connection Error")
					#print('-'*60)
					#traceback.print_exc(file=sys.stdout)
					#print('-'*60)

	def makeRtp(self, payload, frameNbr, marker = 0):
		"""RTP-packetize the video data."""
		version = 2
		padding = 0
		extension = 0
		cc = 0
		# marker = 0
		pt = 26 # MJPEG type
		seqnum = frameNbr
		ssrc = 0 
		
		rtpPacket = RtpPacket()
		
		rtpPacket.encode(version, padding, extension, cc, seqnum, marker, pt, ssrc, payload)
		
		return rtpPacket.getPacket()
		
	def replyRtsp(self, code, seq):
		"""Send RTSP reply to the client."""
		if code == self.OK_200:
			#print("200 OK")
			reply = 'RTSP/1.0 200 OK\nCSeq: ' + seq + '\nSession: ' + str(self.clientInfo['session'])
			connSocket = self.clientInfo['rtspSocket'][0]
			connSocket.send(reply.encode())
		
		# Error messages
		elif code == self.FILE_NOT_FOUND_404:
			print("404 NOT FOUND")
		elif code == self.CON_ERR_500:
			print("500 CONNECTION ERROR")
