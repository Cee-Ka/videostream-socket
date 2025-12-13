class VideoStream:
    def __init__(self, filename):
        self.filename = filename
        try:
            self.file = open(filename, 'rb')
            self.frameNum = 0
            # Đọc toàn bộ file vào bộ nhớ để xử lý nhanh (cho file nhỏ/vừa)
            self.data = self.file.read() 
            self.file.close()
            self.cursor = 0
        except:
            raise IOError

    def nextFrame(self):
        """Get next frame cho MJPEG chuẩn (tìm FF D8 ... FF D9)"""
        if self.cursor >= len(self.data):
            return None

        # Tìm đầu frame (FF D8)
        start = self.data.find(b'\xff\xd8', self.cursor)
        if start == -1:
            return None
        
        # Tìm cuối frame (FF D9)
        end = self.data.find(b'\xff\xd9', start)
        if end == -1:
            return None
        
        end = end + 2 # Lấy cả 2 byte FF D9
        
        # Trích xuất frame
        frame = self.data[start:end]
        
        # Cập nhật vị trí con trỏ và số frame
        self.cursor = end
        self.frameNum += 1
        
        return frame

    def frameNbr(self):
        """Get frame number."""
        return self.frameNum