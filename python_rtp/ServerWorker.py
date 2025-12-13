from random import randint
import sys, traceback, threading, socket, time

from VideoStream import VideoStream
from RtpPacket import RtpPacket
from NetworkStats import NetworkStats

class ServerWorker:
	SETUP = 'SETUP'
	PLAY = 'PLAY'
	PAUSE = 'PAUSE'
	TEARDOWN = 'TEARDOWN'

	MAX_PAYLOAD_SIZE = 1384
	
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
		self.fragmentId = 0
		self.stats = NetworkStats()
		
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
				
				# Send RTSP reply
				self.replyRtsp(self.OK_200, seq[1])
				
				# Get the RTP/UDP port from the last line
				self.clientInfo['rtpPort'] = request[2].split(' ')[3]
				
		# Process PLAY request 		
		elif requestType == self.PLAY:
			if self.state == self.READY:
				print("processing PLAY\n")
				self.state = self.PLAYING
				
				# Create a new socket for RTP/UDP
				self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
				
				self.replyRtsp(self.OK_200, seq[1])
				
				# Create a new thread and start sending RTP packets
				self.clientInfo['event'] = threading.Event()
				self.clientInfo['worker']= threading.Thread(target=self.sendRtp) 
				self.clientInfo['worker'].start()
		
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
		"""Main RTP sending loop with fragmentation support."""
		while True:
			# 50 FPS pacing
			self.clientInfo['event'].wait(0.02)
			
			# Stop sending if request is PAUSE or TEARDOWN
			if self.clientInfo['event'].isSet(): 
				break 
				
			data = self.clientInfo['videoStream'].nextFrame()
			if not data:
				continue

			frameLength = len(data)
			curFrameNbr = self.clientInfo['videoStream'].frameNbr()

			try:
				address = self.clientInfo['rtspSocket'][1][0]
				port = int(self.clientInfo['rtpPort'])
				if frameLength > self.MAX_PAYLOAD_SIZE:
					self.sendFragmentedFrame(data, frameLength, curFrameNbr)
				else:
					rtpPacket = self.makeRtp(data, curFrameNbr)
					self.clientInfo['rtpSocket'].sendto(rtpPacket.getPacket(), (address, port))
					self.stats.recordPacketSent(len(rtpPacket.getPacket()))
					self.stats.recordFrameSent()
			except Exception:
				print("Connection Error")

			# Print statistics every 100 frames
			if curFrameNbr % 100 == 0:
				stats = self.stats.getStats()
				print(
					f"[Server] Frame {curFrameNbr} | "
					f"Size: {frameLength} bytes | "
					f"BW: {stats['bandwidth_sent_kbps']:.1f} Kbps | "
					f"Fragments: {stats['fragments_sent']}"
				)

	def sendFragmentedFrame(self, frameData, frameLength, frameNbr):
		"""Fragment a large frame and send over UDP."""
		totalFragments = (frameLength + self.MAX_PAYLOAD_SIZE - 1) // self.MAX_PAYLOAD_SIZE

		# Increment fragment ID (unique per frame)
		self.fragmentId += 1
		if self.fragmentId > 65535:  # 16-bit limit
			self.fragmentId = 1

		print(
			f"[Server] Fragmenting frame {frameNbr}: "
			f"{frameLength} bytes into {totalFragments} fragments"
		)

		for i in range(totalFragments):
			# Extract fragment payload
			start = i * self.MAX_PAYLOAD_SIZE
			end = min(start + self.MAX_PAYLOAD_SIZE, frameLength)
			fragmentData = frameData[start:end]

			# Create RTP packet with fragment header
			rtpPacket = self.makeRtp(
				fragmentData,
				frameNbr,
				fragment_id=self.fragmentId,
				total_fragments=totalFragments,
				fragment_index=i
			)

			# Send via UDP
			self.clientInfo['rtpSocket'].sendto(
				rtpPacket.getPacket(),
				(self.clientInfo['rtspSocket'][1][0], int(self.clientInfo['rtpPort']))
			)

			# Record statistics
			self.stats.recordPacketSent(len(rtpPacket.getPacket()))
			self.stats.recordFragmentSent()

			# Inter-fragment delay (0.1ms) to avoid congestion
			time.sleep(0.0001)

		# Record frame sent
		self.stats.recordFrameSent()

	def makeRtp(self, payload, frameNbr, fragment_id=0, total_fragments=1, fragment_index=0):
		"""RTP-packetize the video data with optional fragmentation support."""
		version = 2
		padding = 0
		extension = 0
		cc = 0
		marker = 1 if fragment_index == total_fragments - 1 else 0  # Set marker on last fragment
		pt = 26 # MJPEG type
		seqnum = frameNbr
		ssrc = 0 
		
		rtpPacket = RtpPacket()
		
		rtpPacket.encode(
			version,
			padding,
			extension,
			cc,
			seqnum,
			marker,
			pt,
			ssrc,
			payload,
			fragment_id=fragment_id,
			total_fragments=total_fragments,
			fragment_index=fragment_index
		)
		
		return rtpPacket
		
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
