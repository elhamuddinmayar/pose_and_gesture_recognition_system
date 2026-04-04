import os
import cv2
import threading
import time
from django.utils import timezone
from django.db.models import Q
from .models import TargetPerson
from ultralytics import YOLO
from deepface import DeepFace
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

#the deepface address that has been localize in project 
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YOLO_PATH = os.path.join(BASE_DIR, 'surveillance', 'models', 'yolo11n_models', 'yolo11n-pose.pt')
DEEPFACE_MODELS = os.path.join(BASE_DIR, 'surveillance', 'models')

# Configure DeepFace to look in your custom directory
os.environ["DEEPFACE_HOME"] = DEEPFACE_MODELS

class SurveillanceEngine(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.running = False
        self.model = None
        self.channel_layer = get_channel_layer()
        self.targets = []

    def load_resources(self):
        """Load YOLO model once when the thread starts."""
        if self.model is None:
            self.model = YOLO(YOLO_PATH)

    def refresh_targets(self):
        """Fetch active targets from DB."""
        now = timezone.now()
        active = TargetPerson.objects.filter(is_found=False).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        )
        self.targets = [{"name": t.name, "path": t.image.path} for t in active]

    def run(self):
        self.running = True
        self.load_resources()
        cap = cv2.VideoCapture(0)
        frame_count = 0

        while self.running:
            success, frame = cap.read()
            if not success:
                time.sleep(1) # Wait if camera fails
                continue

            # 1. YOLO Pose Detection
            results = self.model.predict(source=frame, conf=0.5, verbose=False)
            person_count = len(results[0].boxes) if results else 0
            detected_action = "Normal"

            # Logic for Actions (Simplified for brevity)
            if results and len(results[0].keypoints) > 0:
                for kpts in results[0].keypoints.data:
                    k = kpts.cpu().numpy()
                    try:
                        if k[0][1] > k[11][1]: detected_action = "FALL DETECTED"
                        elif k[9][1] < k[0][1]: detected_action = "HAND WAVING"
                    except: continue

            # 2. Sync Targets from DB every 10 seconds
            if frame_count % 300 == 0:
                self.refresh_targets()

            # 3. DeepFace Check (Every 50 frames)
            if frame_count % 50 == 0 and person_count > 0 and self.targets:
                for target in self.targets:
                    try:
                        # VGG-Face path is handled via DEEPFACE_HOME env var
                        res = DeepFace.verify(img1_path=frame, img2_path=target['path'], 
                                              enforce_detection=False, model_name="VGG-Face")
                        if res['verified']:
                            self.broadcast({"type": "TARGET_MATCH", "name": target['name']})
                    except: continue

            # 4. Broadcast Live Stats to Dashboard Group
            self.broadcast({
                "type": "STAT_UPDATE",
                "count": person_count,
                "action": detected_action,
                "message": f"{person_count} Detected | {detected_action}"
            })

            frame_count += 1
            time.sleep(0.01)

    def broadcast(self, data):
        """Send data to the Django Channels group."""
        async_to_sync(self.channel_layer.group_send)(
            "surveillance_group",
            {"type": "forward_to_websocket", "payload": data}
        )

# Initialize the global instance
monitor = SurveillanceEngine()