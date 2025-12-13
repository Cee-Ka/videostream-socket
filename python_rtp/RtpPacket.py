import sys
from time import time

HEADER_SIZE = 12
FRAGMENT_HEADER_SIZE = 4


class RtpPacket:
	header = bytearray(HEADER_SIZE)

	def __init__(self):
		self.fragmentHeader = None
		self.payload = b''

	def encode(self, version, padding, extension, cc, seqnum, marker, pt, ssrc, payload, fragment_id=0, total_fragments=1, fragment_index=0):
		"""Encode the RTP packet with header fields and payload."""
		timestamp = int(time())
		header = bytearray(HEADER_SIZE)

		# Fill the header bytearray with RTP header fields
		header[0] = (version << 6) | (padding << 5) | (extension << 4) | cc
		header[1] = (marker << 7) | pt
		header[2] = (seqnum >> 8) & 0xFF
		header[3] = seqnum & 0xFF

		header[4] = (timestamp >> 24) & 0xFF
		header[5] = (timestamp >> 16) & 0xFF
		header[6] = (timestamp >> 8) & 0xFF
		header[7] = timestamp & 0xFF

		header[8] = (ssrc >> 24) & 0xFF
		header[9] = (ssrc >> 16) & 0xFF
		header[10] = (ssrc >> 8) & 0xFF
		header[11] = ssrc & 0xFF
		self.header = header

		# Add fragmentation header if this is a fragmented packet
		if total_fragments > 1:
			self.fragmentHeader = bytearray(FRAGMENT_HEADER_SIZE)
			self.fragmentHeader[0] = (fragment_id >> 8) & 0xFF
			self.fragmentHeader[1] = fragment_id & 0xFF
			self.fragmentHeader[2] = total_fragments & 0xFF
			self.fragmentHeader[3] = fragment_index & 0xFF
		else:
			self.fragmentHeader = None

		# Get the payload from the argument
		self.payload = payload

	def decode(self, byteStream):
		"""Decode the RTP packet."""
		self.header = bytearray(byteStream[:HEADER_SIZE])
		payload = byteStream[HEADER_SIZE:]
		self.fragmentHeader = None

		if len(payload) >= FRAGMENT_HEADER_SIZE + 2:
			# Heuristic: Fragmented payloads start with fragment header, non-fragmented MJPEG starts with 0xFFD8
			if not (payload[0] == 0xFF and payload[1] == 0xD8):
				self.fragmentHeader = bytearray(payload[:FRAGMENT_HEADER_SIZE])
				self.payload = payload[FRAGMENT_HEADER_SIZE:]
				return

		self.payload = payload

	def version(self):
		"""Return RTP version."""
		return int(self.header[0] >> 6)

	def seqNum(self):
		"""Return sequence (frame) number."""
		seqNum = self.header[2] << 8 | self.header[3]
		return int(seqNum)

	def timestamp(self):
		"""Return timestamp."""
		timestamp = self.header[4] << 24 | self.header[5] << 16 | self.header[6] << 8 | self.header[7]
		return int(timestamp)

	def payloadType(self):
		"""Return payload type."""
		pt = self.header[1] & 127
		return int(pt)

	def getPayload(self):
		"""Return payload."""
		return self.payload

	def getPacket(self):
		"""Return RTP packet."""
		packet = self.header
		if self.fragmentHeader:
			packet += self.fragmentHeader
		return packet + self.payload

	def isFragmented(self):
		"""Check if this packet is part of a fragmented frame."""
		return self.fragmentHeader is not None

	def getFragmentId(self):
		"""Return fragment ID."""
		if self.fragmentHeader:
			return (self.fragmentHeader[0] << 8) | self.fragmentHeader[1]
		return 0

	def getTotalFragments(self):
		"""Return total number of fragments."""
		if self.fragmentHeader:
			return self.fragmentHeader[2]
		return 1

	def getFragmentIndex(self):
		"""Return fragment index."""
		if self.fragmentHeader:
			return self.fragmentHeader[3]
		return 0
