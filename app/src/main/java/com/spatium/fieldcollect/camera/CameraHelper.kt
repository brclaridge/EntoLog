package com.spatium.fieldcollect.camera

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.net.Uri
import android.provider.MediaStore
import androidx.core.content.FileProvider
import androidx.exifinterface.media.ExifInterface
import java.io.File

class CameraHelper(private val context: Context) {

    private var currentPhotoPath: String? = null

    fun getPhotosDir(): File {
        val dir = File(context.filesDir, "photos")
        if (!dir.exists()) dir.mkdirs()
        return dir
    }

    /**
     * Creates a uniquely-named photo file and returns (content URI, file path).
     * Uses recordUuid + timestamp to allow multiple photos per record.
     */
    fun createPhotoFile(recordUuid: String): Pair<Uri, String> {
        val timestamp = System.currentTimeMillis()
        val file = File(getPhotosDir(), "${recordUuid}_${timestamp}.jpg")
        currentPhotoPath = file.absolutePath
        val uri = FileProvider.getUriForFile(
            context,
            "${context.packageName}.fileprovider",
            file
        )
        return Pair(uri, file.absolutePath)
    }

    fun createCaptureIntent(photoUri: Uri): Intent {
        return Intent(MediaStore.ACTION_IMAGE_CAPTURE).apply {
            putExtra(MediaStore.EXTRA_OUTPUT, photoUri)
        }
    }

    fun getLastPhotoPath(): String? = currentPhotoPath

    fun listPhotos(): List<File> {
        return getPhotosDir().listFiles()?.toList() ?: emptyList()
    }

    companion object {
        /**
         * Loads a bitmap from file with EXIF rotation correction and downsampling.
         * @param sampleSize BitmapFactory inSampleSize (8 for thumbnails, 2 for previews)
         */
        fun loadBitmap(path: String, sampleSize: Int = 1): Bitmap? {
            val file = File(path)
            if (!file.exists()) return null

            val options = BitmapFactory.Options().apply { inSampleSize = sampleSize }
            val bitmap = BitmapFactory.decodeFile(path, options) ?: return null

            val rotation = try {
                val exif = ExifInterface(path)
                when (exif.getAttributeInt(
                    ExifInterface.TAG_ORIENTATION,
                    ExifInterface.ORIENTATION_NORMAL
                )) {
                    ExifInterface.ORIENTATION_ROTATE_90 -> 90f
                    ExifInterface.ORIENTATION_ROTATE_180 -> 180f
                    ExifInterface.ORIENTATION_ROTATE_270 -> 270f
                    else -> 0f
                }
            } catch (e: Exception) {
                0f
            }

            return if (rotation != 0f) {
                val matrix = Matrix().apply { postRotate(rotation) }
                Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
            } else {
                bitmap
            }
        }
    }
}
