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
        request = data.split('\n')
        line1 = request[0].split(' ')
        requestType = line1[0]
        filename = line1[1]
        seq = request[1].split(' ')
        
        # Process SETUP request
        if requestType == self.SETUP:
            if self.state == self.INIT:
                print("processing SETUP\n")
                try:
                    self.clientInfo['videoStream'] = VideoStream(filename)
                    self.state = self.READY
                except IOError:
                    self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
                
                self.clientInfo['session'] = randint(100000, 999999)
                self.clientInfo['rtpPort'] = request[2].split(' ')[3]
                self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.replyRtsp(self.OK_200, seq[1])
                
        # Process PLAY request      
        elif requestType == self.PLAY:
            if self.state == self.READY:
                print("processing PLAY\n")
                self.state = self.PLAYING
                
                # Tạo thread gửi RTP mới
                self.clientInfo['event'] = threading.Event()
                self.clientInfo['worker'] = threading.Thread(target=self.sendRtp) 
                self.clientInfo['worker'].start()
                
                self.replyRtsp(self.OK_200, seq[1])
        
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
            self.clientInfo['rtpSocket'].close()
            
    def sendRtp(self):
        """Send RTP packets over UDP."""
        MAX_PAYLOAD_SIZE = 1400 
        
        while True:
            self.clientInfo['event'].wait(0.05) 
            
            if self.clientInfo['event'].isSet(): 
                break 
                
            data = self.clientInfo['videoStream'].nextFrame()
            if data: 
                frameNumber = self.clientInfo['videoStream'].frameNbr()
                try:
                    address = self.clientInfo['rtspSocket'][1][0]
                    port = int(self.clientInfo['rtpPort'])

                    # Logic Fragmentation (Cắt nhỏ gói tin HD)
                    data_len = len(data)
                    curr_pos = 0
                    while curr_pos < data_len:
                        chunk = data[curr_pos : curr_pos + MAX_PAYLOAD_SIZE]
                        curr_pos += MAX_PAYLOAD_SIZE
                        
                        if curr_pos >= data_len:
                            marker = 1
                        else:
                            marker = 0
                        
                        self.clientInfo['rtpSocket'].sendto(self.makeRtp(chunk, frameNumber, marker),(address,port))
                except:
                    print("Connection Error")

    def makeRtp(self, payload, frameNbr, marker = 0):
        """RTP-packetize the video data."""
        version = 2
        padding = 0
        extension = 0
        cc = 0
        pt = 26 
        seqnum = frameNbr
        ssrc = 0 
        
        rtpPacket = RtpPacket()
        rtpPacket.encode(version, padding, extension, cc, seqnum, marker, pt, ssrc, payload)
        return rtpPacket.getPacket()
        
    def replyRtsp(self, code, seq):
        """Send RTSP reply to the client."""
        if code == self.OK_200:
            reply = 'RTSP/1.0 200 OK\nCSeq: ' + seq + '\nSession: ' + str(self.clientInfo['session'])
            connSocket = self.clientInfo['rtspSocket'][0]
            connSocket.send(reply.encode())
        elif code == self.FILE_NOT_FOUND_404:
            print("404 NOT FOUND")
        elif code == self.CON_ERR_500:
            print("500 CONNECTION ERROR")