from django.apps import AppConfig
import sys,os

class SurveillanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'surveillance'

    def ready(self):
        # Ensure we only start the camera once, even with the reloader active
        if 'runserver' in sys.argv and os.environ.get('RUN_MAIN') == 'true':
            #catch data from engine to handle for system and it will start automatically by running server
            from .engine import monitor
            if not monitor.is_alive():
                print("--- Starting Background Surveillance Engine ---")
                monitor.start()