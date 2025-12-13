import time


class NetworkStats:
	def __init__(self):
		self.startTime = time.time()
		self.totalPacketsSent = 0
		self.totalPacketsReceived = 0
		self.packetsLost = 0
		self.totalBytesSent = 0
		self.totalBytesReceived = 0

		self.framesSent = 0
		self.framesReceived = 0
		self.framesLost = 0

		self.fragmentsSent = 0
		self.fragmentsReceived = 0

	def _elapsed(self):
		elapsed = time.time() - self.startTime
		return elapsed if elapsed > 0 else 1e-6

	def recordPacketSent(self, size_bytes=0):
		self.totalPacketsSent += 1
		self.totalBytesSent += size_bytes

	def recordPacketReceived(self, size_bytes=0):
		self.totalPacketsReceived += 1
		self.totalBytesReceived += size_bytes

	def recordPacketLost(self, count=1):
		self.packetsLost += count

	def recordFrameSent(self):
		self.framesSent += 1

	def recordFrameReceived(self):
		self.framesReceived += 1

	def recordFrameLost(self, count=1):
		self.framesLost += count

	def recordFragmentSent(self):
		self.fragmentsSent += 1

	def recordFragmentReceived(self):
		self.fragmentsReceived += 1

	def getStats(self):
		elapsed = self._elapsed()
		bandwidth_sent_kbps = (self.totalBytesSent * 8) / (elapsed * 1024)
		bandwidth_recv_kbps = (self.totalBytesReceived * 8) / (elapsed * 1024)

		return {
			'packets_sent': self.totalPacketsSent,
			'packets_received': self.totalPacketsReceived,
			'packets_lost': self.packetsLost,
			'frames_sent': self.framesSent,
			'frames_received': self.framesReceived,
			'frames_lost': self.framesLost,
			'fragments_sent': self.fragmentsSent,
			'fragments_received': self.fragmentsReceived,
			'bandwidth_sent_kbps': bandwidth_sent_kbps,
			'bandwidth_received_kbps': bandwidth_recv_kbps,
			'total_bytes_sent': self.totalBytesSent,
			'total_bytes_received': self.totalBytesReceived,
			'elapsed_seconds': elapsed,
		}

	def getStatsString(self):
		stats = self.getStats()
		return (
			f"Packets: sent={stats['packets_sent']} recv={stats['packets_received']} lost={stats['packets_lost']} | "
			f"Frames: sent={stats['frames_sent']} recv={stats['frames_received']} lost={stats['frames_lost']} | "
			f"Fragments: sent={stats['fragments_sent']} recv={stats['fragments_received']} | "
			f"BW: sent={stats['bandwidth_sent_kbps']:.1f}kbps recv={stats['bandwidth_received_kbps']:.1f}kbps"
		)
