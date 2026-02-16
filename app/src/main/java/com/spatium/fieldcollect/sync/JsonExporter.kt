package com.spatium.fieldcollect.sync

import android.content.Context
import com.spatium.fieldcollect.data.db.entity.CollectingEventWithCollectors
import com.spatium.fieldcollect.data.db.entity.Photo
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

class JsonExporter(private val context: Context) {

    private fun exportDir(): File {
        val dir = File(context.filesDir, "export")
        if (!dir.exists()) dir.mkdirs()
        return dir
    }

    fun exportCollectingEvents(
        records: List<CollectingEventWithCollectors>,
        photosByRecord: Map<String, List<Photo>>
    ): File {
        val jsonArray = JSONArray()

        for (r in records) {
            val e = r.event
            val photos = photosByRecord[e.uuid] ?: emptyList()

            val obj = JSONObject().apply {
                put("collectionCode", e.collectionCode)
                put("uuid", e.uuid)
                put("latitude", e.latitude ?: JSONObject.NULL)
                put("longitude", e.longitude ?: JSONObject.NULL)
                put("elevation", e.elevation ?: JSONObject.NULL)
                put("gpsAccuracy", e.gpsAccuracy?.toDouble() ?: JSONObject.NULL)
                put("createdAt", e.createdAt)
                put("country", e.country)
                put("stateProvince", e.stateProvince)
                put("county", e.county)
                put("locality", e.locality)
                put("host", e.host)
                put("collectionTechnique", e.collectionTechnique ?: JSONObject.NULL)
                put("notes", e.notes)
                put("startDateTime", e.startDateTime ?: JSONObject.NULL)
                put("endDateTime", e.endDateTime ?: JSONObject.NULL)
                put("coordPrecision", e.coordPrecision)
                put("modifiedAt", e.modifiedAt ?: JSONObject.NULL)
                put("collectors", JSONArray(r.collectors.map { it.name }))
                put("photos", JSONArray(photos.map { File(it.filePath).name }))
            }

            jsonArray.put(obj)
        }

        val file = File(exportDir(), "collectingEvents.json")
        file.writeText(jsonArray.toString(2))
        return file
    }
}
