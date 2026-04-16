"""
Android camera-capture helper for the Kivy mobile app.

This module wraps Android's camera intent flow so the app can capture a photo
directly into a chosen file path and receive the result asynchronously.
"""

import os

from kivy.clock import Clock
from kivy.utils import platform


class AndroidCameraCapture:
    """
    Helper class for launching the Android camera and receiving the captured image path.
    """

    REQUEST_CODE_CAMERA = 1001

    def __init__(self):
        """
        Initialize the camera helper state.
        """
        self._callback = None
        self._current_photo_path = None
        self._bound = False

    def capture(self, output_path, callback):
        """
        Launch the Android camera app and request that the captured photo be saved
        to the given output path.

        Parameters:
            output_path (str): Destination file path for the captured image.
            callback (callable): Function called later with the saved image path.

        Raises:
            RuntimeError: If called on a non-Android platform.
        """
        if platform != "android":
            raise RuntimeError("Android camera capture helper can only run on Android.")

        self._callback = callback
        self._current_photo_path = output_path

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        from jnius import autoclass, cast
        from android import activity

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Intent = autoclass("android.content.Intent")
        MediaStore = autoclass("android.provider.MediaStore")
        File = autoclass("java.io.File")
        FileProvider = autoclass("androidx.core.content.FileProvider")

        current_activity = PythonActivity.mActivity
        context = cast("android.content.Context", current_activity)

        photo_file = File(output_path)
        authority = current_activity.getPackageName() + ".fileprovider"

        # Use a FileProvider URI so the external camera app can write to the
        # app-owned output file safely.
        photo_uri = FileProvider.getUriForFile(
            context,
            authority,
            photo_file
        )

        intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
        intent.putExtra(
            MediaStore.EXTRA_OUTPUT,
            cast("android.os.Parcelable", photo_uri)
        )
        intent.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)

        # Bind to activity results only while a capture request is active.
        if not self._bound:
            activity.bind(on_activity_result=self._on_activity_result)
            self._bound = True

        current_activity.startActivityForResult(intent, self.REQUEST_CODE_CAMERA)

    def _on_activity_result(self, request_code, result_code, intent):
        """
        Internal Android activity-result callback.

        When the camera activity returns, the stored callback is invoked on the
        Kivy main thread with the saved image path.

        Parameters:
            request_code (int): Activity request code.
            result_code (int): Android result code.
            intent: Returned Android intent object.
        """
        if request_code != self.REQUEST_CODE_CAMERA:
            return

        from android import activity

        if self._bound:
            activity.unbind(on_activity_result=self._on_activity_result)
            self._bound = False

        path = self._current_photo_path

        if self._callback is not None:
            callback = self._callback
            self._callback = None
            self._current_photo_path = None

            # Schedule the callback on the Kivy event loop thread.
            Clock.schedule_once(lambda dt: callback(path), 0)
