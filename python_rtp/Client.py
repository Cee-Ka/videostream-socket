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

        # Thống kê
        self.totalBytesReceived = 0 
        self.startTime = 0          
        self.endTime = 0            
        self.totalFramesReceived = 0 

        # Buffer: Tăng size để tránh packet loss khi mạng nhanh
        self.frameBuffer = queue.Queue(maxsize=600)
        self.incompleteFrame = b''
        self.bufferStarted = False
        
        # Để detect packet/frame loss (seqNum = frame number, không phải packet number)
        self.currentFrameSeq = -1  # frame đang nhận
        self.lastCompletedFrameSeq = -1  # frame hoàn chỉnh gần nhất
        
        # Bandwidth protection - đơn giản và hiệu quả
        self.droppedFrames = 0  # đếm frame bị drop
        self.BUFFER_WARNING = 400  # ngưỡng cảnh báo (67% của 600)
        self.BUFFER_CRITICAL = 550  # ngưỡng nguy hiểm (92% của 600)

    def resetVideo(self):
        """Reset trạng thái để reload."""
        self.frameNbr = 0
        self.incompleteFrame = b''
        self.bufferStarted = False

        self.currentFrameSeq = -1
        self.lastCompletedFrameSeq = -1
        self.droppedFrames = 0
        
        with self.frameBuffer.mutex:
            self.frameBuffer.queue.clear()
        self.totalBytesReceived = 0
        self.startTime = 0
        self.endTime = 0
        self.totalFramesReceived = 0
        try:
            os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT)
        except OSError:
            pass    

    def createWidgets(self):
        """Build GUI với khả năng co giãn."""
        self.master.grid_rowconfigure(0, weight=1)
        self.master.grid_columnconfigure(0, weight=1)
        
        self.setup = Button(self.master, width=20, padx=3, pady=3, text="Setup", command=self.setupMovie)
        self.setup.grid(row=1, column=0, padx=2, pady=2)
        
        self.start = Button(self.master, width=20, padx=3, pady=3, text="Play", command=self.playMovie)
        self.start.grid(row=1, column=1, padx=2, pady=2)
        
        self.pause = Button(self.master, width=20, padx=3, pady=3, text="Pause", command=self.pauseMovie)
        self.pause.grid(row=1, column=2, padx=2, pady=2)
        
        self.teardown = Button(self.master, width=20, padx=3, pady=3, text="Teardown", command=self.exitClient)
        self.teardown.grid(row=1, column=3, padx=2, pady=2)
        
        # Label nền đen, tự co giãn
        self.label = Label(self.master)
        self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 

    def setupMovie(self):
        if self.state == self.INIT:
            self.sendRtspRequest(self.SETUP)

    def exitClient(self):
        try:
            self.playEvent.set()
        except:
            pass
        self.sendRtspRequest(self.TEARDOWN)
        
        # --- REPORT ---
        print("\n" + "="*40)
        print("       VIDEO STREAMING SESSION REPORT       ")
        print("="*40)
        duration = self.endTime - self.startTime
        if duration <= 0: duration = 1
        
        expectedFrames = self.frameNbr
        if expectedFrames > 0:
            lostFrames = expectedFrames - self.totalFramesReceived
            lossRate = (lostFrames / expectedFrames) * 100
        else:
            lostFrames = 0
            lossRate = 0.0
            
        totalKbits = (self.totalBytesReceived * 8) / 1000
        bitrate = totalKbits / duration
        
        print(f"Total Duration      : {duration:.2f} seconds")
        print(f"Total Bytes Received: {self.totalBytesReceived / 1024:.2f} KB")
        print(f"Average Bitrate     : {bitrate:.2f} kbps")
        print("-" * 40)
        print(f"Max Sequence Number : {expectedFrames}")
        print(f"Total Frames Decoded: {self.totalFramesReceived}")
        print(f"Frames Lost         : {lostFrames}")
        print(f"Packet Loss Rate    : {lossRate:.2f} %")
        print("="*40 + "\n")

        self.master.destroy() 
        try:
            os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT) 
        except:
            pass

    def pauseMovie(self):
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)

    def playMovie(self):
        if self.state == self.READY:
            self.playEvent = threading.Event()
            self.playEvent.clear()

            # Server gửi lúc Play -> Start cả 2 luồng tại đây
            threading.Thread(target=self.listenRtp).start()
            threading.Thread(target=self.consumeBuffer).start()
            
            self.sendRtspRequest(self.PLAY)

    def listenRtp(self):        
        while True:
            try:
                data = self.rtpSocket.recv(20480)
                if data:
                    curTime = time.time()
                    if self.startTime == 0: self.startTime = curTime
                    self.endTime = curTime
                    self.totalBytesReceived += len(data)

                    rtpPacket = RtpPacket()
                    rtpPacket.decode(data)
                    
                    currSeqNum = rtpPacket.seqNum()  # = frame number (tất cả packet cùng frame có cùng seqNum)
                    
                    # Nếu đây là packet của frame mới (seqNum khác với frame đang nhận)
                    if currSeqNum != self.currentFrameSeq:
                        # Nếu đang có frame dở dang mà chưa nhận được marker -> packet loss
                        if self.currentFrameSeq != -1 and self.incompleteFrame:
                            print(f"[PACKET LOSS] Frame {self.currentFrameSeq} incomplete, discarding. New frame {currSeqNum} started.")
                            self.incompleteFrame = b''
                        self.currentFrameSeq = currSeqNum
                    
                    # Accumulate payload cho frame hiện tại
                    self.incompleteFrame += rtpPacket.getPayload()

                    if rtpPacket.getMarker() == 1:
                        # Đây là packet cuối của frame
                        # Kiểm tra xem có bị mất frame nào không (gap trong sequence)
                        if self.lastCompletedFrameSeq != -1 and currSeqNum > self.lastCompletedFrameSeq + 1:
                            lostFrames = currSeqNum - self.lastCompletedFrameSeq - 1
                            print(f"[FRAME LOSS] Skipped {lostFrames} frame(s) between seq {self.lastCompletedFrameSeq} and {currSeqNum}")
                        
                        # Frame hoàn chỉnh, đưa vào buffer
                        self.totalFramesReceived += 1
                        
                        if currSeqNum > self.frameNbr:
                            self.frameNbr = currSeqNum
                            try:
                                self.frameBuffer.put(self.incompleteFrame, timeout=1.0)
                            except queue.Full:
                                pass
                        
                        # Cập nhật tracking
                        self.lastCompletedFrameSeq = currSeqNum
                        self.incompleteFrame = b''
                        self.currentFrameSeq = -1
            except:
                if self.playEvent.isSet(): break
                if self.teardownAcked == 1:
                    self.rtpSocket.shutdown(socket.SHUT_RDWR)
                    self.rtpSocket.close()
                    break

    def consumeBuffer(self):
        FRAME_DELAY_NORMAL = 0.05   # 20 fps bình thường
        FRAME_DELAY_FAST = 0.025    # 40 fps khi cần catch up
        PRE_BUFFER = 20    

        while True:
            if self.playEvent.isSet(): break

            if not self.bufferStarted:
                if self.frameBuffer.qsize() >= PRE_BUFFER:
                    self.bufferStarted = True
                    print("Buffering complete. Starting playback...")
                else:
                    threading.Event().wait(0.1)
                    continue

            bufferSize = self.frameBuffer.qsize()
            
            # === BANDWIDTH PROTECTION ===
            # Mức CRITICAL: drop nhiều frame để tránh overflow
            if bufferSize >= self.BUFFER_CRITICAL:
                framesToDrop = bufferSize - self.BUFFER_WARNING
                for _ in range(framesToDrop):
                    if not self.frameBuffer.empty():
                        self.frameBuffer.get()  # discard
                        self.droppedFrames += 1
                print(f"[BANDWIDTH] Critical! Dropped {framesToDrop} frames. Buffer: {self.frameBuffer.qsize()}")
            
            # Mức WARNING: drop 1 frame mỗi 2 frame để giảm dần
            elif bufferSize >= self.BUFFER_WARNING:
                if not self.frameBuffer.empty():
                    self.frameBuffer.get()  # drop 1 frame
                    self.droppedFrames += 1

            if not self.frameBuffer.empty():
                frameData = self.frameBuffer.get()
                try:
                    path = self.writeFrame(frameData)
                    self.updateMovie(path)
                except Exception as e:
                    print(f"Skipping bad frame: {e}")
                
                # Adaptive delay: nhanh hơn khi buffer lớn
                if bufferSize > self.BUFFER_WARNING // 2:
                    threading.Event().wait(FRAME_DELAY_FAST)
                else:
                    threading.Event().wait(FRAME_DELAY_NORMAL)
            else:
                threading.Event().wait(0.01)

    def writeFrame(self, data):
        cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        with open(cachename, "wb") as file:
            file.write(data)
        return cachename

    def updateMovie(self, imageFile):
        """Update the image file as video frame in the GUI."""
        photo = ImageTk.PhotoImage(Image.open(imageFile))
        self.label.configure(image = photo) 
        self.label.image = photo

    def connectToServer(self):
        self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.rtspSocket.connect((self.serverAddr, self.serverPort))
        except:
            tkMessageBox.showwarning('Connection Failed', 'Connection to \'%s\' failed.' %self.serverAddr)

    def sendRtspRequest(self, requestCode):
        if requestCode == self.SETUP and self.state == self.INIT:
            threading.Thread(target=self.recvRtspReply).start()
            self.rtspSeq += 1
            request = f"SETUP {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nTransport: RTP/UDP; client_port= {self.rtpPort}\n"
            self.requestSent = self.SETUP
        
        elif requestCode == self.PLAY and self.state == self.READY:
            self.rtspSeq += 1
            request = f"PLAY {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}"
            self.requestSent = self.PLAY
        
        elif requestCode == self.PAUSE and self.state == self.PLAYING:
            self.rtspSeq += 1
            request = f"PAUSE {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}"
            self.requestSent = self.PAUSE
            
        elif requestCode == self.TEARDOWN and not self.state == self.INIT:
            self.rtspSeq += 1
            request = f"TEARDOWN {self.fileName} RTSP/1.0\nCseq: {self.rtspSeq}\nSession: {self.sessionId}"
            self.requestSent = self.TEARDOWN
        else:
            return
        
        self.rtspSocket.send(request.encode("utf-8"))
        print('\nData sent:\n' + request)

    def recvRtspReply(self):
        while True:
            try:
                reply = self.rtspSocket.recv(1024)
                if reply: 
                    self.parseRtspReply(reply.decode("utf-8"))
                if self.requestSent == self.TEARDOWN:
                    self.rtspSocket.shutdown(socket.SHUT_RDWR)
                    self.rtspSocket.close()
                    break
            except:
                break

    def parseRtspReply(self, data):
        lines = data.split('\n')
        seqNum = int(lines[1].split(' ')[1])
        if seqNum == self.rtspSeq:
            session = int(lines[2].split(' ')[1])
            if self.sessionId == 0: self.sessionId = session
            if self.sessionId == session:
                if int(lines[0].split(' ')[1]) == 200: 
                    if self.requestSent == self.SETUP:
                        self.state = self.READY
                        self.openRtpPort() 
                    elif self.requestSent == self.PLAY:
                        self.state = self.PLAYING
                    elif self.requestSent == self.PAUSE:
                        self.state = self.READY
                        self.playEvent.set()
                    elif self.requestSent == self.TEARDOWN:
                        self.state = self.INIT
                        self.teardownAcked = 1 
                        self.resetVideo() # Reload support

    def openRtpPort(self):
        self.rtpSocket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.rtpSocket.settimeout(0.5)
        try:
            self.rtpSocket.bind(("", self.rtpPort))
        except:
            tkMessageBox.showwarning('Unable to Bind', 'Unable to bind PORT=%d' %self.rtpPort)

    def handler(self):
        self.pauseMovie()
        if tkMessageBox.askokcancel("Quit?", "Are you sure you want to quit?"):
            self.exitClient()
        else: 
            self.playMovie()