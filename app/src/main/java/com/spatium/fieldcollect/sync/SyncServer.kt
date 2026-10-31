package com.spatium.fieldcollect.sync

import android.content.Context
import com.spatium.fieldcollect.FieldCollectApp
import com.spatium.fieldcollect.data.db.entity.CollectingEvent
import com.spatium.fieldcollect.data.repository.FieldRepository
import fi.iki.elonen.NanoHTTPD
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileInputStream
import java.security.MessageDigest

class SyncServer(
    private val context: Context,
    port: Int = 8080,
    private val pairingToken: String
) : NanoHTTPD(port) {

    private val repo = FieldRepository((context.applicationContext as FieldCollectApp).database)
    private val jsonExporter = JsonExporter(context)
    private val photosDir = File(context.filesDir, "photos")

    private val authLock = Any()
    private var failedAttempts = 0
    private var lockedUntilMs = 0L

    // A 4-digit code only has 10,000 possibilities, so unlike a long random
    // token it needs a brute-force throttle: each wrong guess adds delay
    // before the next one is even checked, capped at 5s.
    private fun isAuthorized(session: IHTTPSession): Boolean {
        synchronized(authLock) {
            if (System.currentTimeMillis() < lockedUntilMs) return false
        }
        val provided = session.headers["x-sync-token"]
        val ok = provided != null && MessageDigest.isEqual(
            provided.toByteArray(Charsets.UTF_8),
            pairingToken.toByteArray(Charsets.UTF_8)
        )
        synchronized(authLock) {
            if (ok) {
                failedAttempts = 0
            } else {
                failedAttempts++
                val delayMs = minOf(failedAttempts * 500L, 5000L)
                lockedUntilMs = System.currentTimeMillis() + delayMs
            }
        }
        return ok
    }

    override fun serve(session: IHTTPSession): Response {
        val uri = session.uri
        val method = session.method

        if (!isAuthorized(session)) {
            return newFixedLengthResponse(
                Response.Status.UNAUTHORIZED,
                MIME_PLAINTEXT,
                "Unauthorized: missing or invalid pairing code"
            )
        }

        return when {
            method == Method.GET && uri == "/api/events" -> serveEvents()
            method == Method.GET && uri == "/api/photos" -> servePhotoList()
            method == Method.GET && uri.startsWith("/api/photos/") -> servePhoto(uri)
            method == Method.POST && uri == "/api/events" -> receiveEvents(session)
            else -> newFixedLengthResponse(
                Response.Status.NOT_FOUND,
                MIME_PLAINTEXT,
                "Not found"
            )
        }
    }

    private fun serveEvents(): Response {
        return try {
            val events = runBlocking { repo.getAllCollectingEventsSync() }
            val allPhotos = runBlocking { repo.getAllPhotosSync() }
            val photosByRecord = allPhotos.groupBy { it.recordUuid }
            val file = jsonExporter.exportCollectingEvents(events, photosByRecord)
            val json = file.readText(Charsets.UTF_8)
            newFixedLengthResponse(Response.Status.OK, "application/json", json)
        } catch (e: Exception) {
            newFixedLengthResponse(
                Response.Status.INTERNAL_ERROR,
                MIME_PLAINTEXT,
                "Error: ${e.message}"
            )
        }
    }

    private fun servePhotoList(): Response {
        val files = photosDir.listFiles()?.map { it.name } ?: emptyList()
        val arr = JSONArray(files)
        return newFixedLengthResponse(Response.Status.OK, "application/json", arr.toString())
    }

    private fun servePhoto(uri: String): Response {
        val filename = uri.removePrefix("/api/photos/")
        if (filename.contains("..") || filename.contains("/")) {
            return newFixedLengthResponse(
                Response.Status.FORBIDDEN,
                MIME_PLAINTEXT,
                "Forbidden"
            )
        }
        val file = File(photosDir, filename)
        if (!file.exists() || !file.isFile) {
            return newFixedLengthResponse(
                Response.Status.NOT_FOUND,
                MIME_PLAINTEXT,
                "Photo not found"
            )
        }
        val fis = FileInputStream(file)
        return newFixedLengthResponse(Response.Status.OK, "image/jpeg", fis, file.length())
    }

    private fun receiveEvents(session: IHTTPSession): Response {
        return try {
            val contentLength = session.headers["content-length"]?.toIntOrNull() ?: 0
            val buf = ByteArray(contentLength)
            session.inputStream.read(buf, 0, contentLength)
            val body = String(buf, Charsets.UTF_8)

            val result = runBlocking { importRemoteEvents(body) }
            val response = JSONObject().apply {
                put("ok", true)
                put("imported", result.imported)
                put("updated", result.updated)
            }
            newFixedLengthResponse(Response.Status.OK, "application/json", response.toString())
        } catch (e: Exception) {
            val response = JSONObject().apply {
                put("ok", false)
                put("error", e.message ?: "Unknown error")
            }
            newFixedLengthResponse(
                Response.Status.INTERNAL_ERROR,
                "application/json",
                response.toString()
            )
        }
    }

    private data class ImportResult(val imported: Int, val updated: Int)

    private fun isRemoteNewer(remoteModified: String?, localModified: String?): Boolean {
        if (remoteModified.isNullOrBlank()) return false
        if (localModified.isNullOrBlank()) return true
        return remoteModified > localModified
    }

    private fun parseEventFromJson(obj: JSONObject, uuid: String, technique: String?): CollectingEvent {
        return CollectingEvent(
            uuid = uuid,
            collectionCode = obj.optString("collectionCode", ""),
            latitude = parseNullableDouble(obj, "latitude"),
            longitude = parseNullableDouble(obj, "longitude"),
            elevation = parseNullableInt(obj, "elevation"),
            gpsAccuracy = parseNullableFloat(obj, "gpsAccuracy"),
            createdAt = obj.optString("createdAt", ""),
            country = obj.optString("country", ""),
            stateProvince = obj.optString("stateProvince", ""),
            county = obj.optString("county", ""),
            locality = obj.optString("locality", ""),
            host = obj.optString("host", ""),
            collectionTechnique = technique,
            notes = obj.optString("notes", ""),
            startDateTime = if (obj.isNull("startDateTime")) null else obj.optString("startDateTime"),
            endDateTime = if (obj.isNull("endDateTime")) null else obj.optString("endDateTime"),
            coordPrecision = obj.optInt("coordPrecision", 5).let { if (it <= 0) 5 else it },
            modifiedAt = if (obj.isNull("modifiedAt")) null else obj.optString("modifiedAt")
        )
    }

    private suspend fun resolveCollectorIds(
        obj: JSONObject,
        collectorMap: MutableMap<String, Long>
    ): List<Long> {
        val collectorIds = mutableListOf<Long>()
        val collectorsJson = obj.optJSONArray("collectors") ?: JSONArray()
        for (j in 0 until collectorsJson.length()) {
            val name = collectorsJson.optString(j).trim()
            if (name.isBlank()) continue
            val key = name.lowercase()
            val id = collectorMap[key] ?: run {
                val newId = repo.insertCollector(name)
                if (newId > 0) {
                    collectorMap[key] = newId
                    newId
                } else {
                    val refreshed = repo.getAllCollectorsSync()
                        .firstOrNull { it.name.trim().equals(name, ignoreCase = true) }
                    refreshed?.id?.also { collectorMap[key] = it } ?: 0L
                }
            }
            if (id > 0) collectorIds.add(id)
        }
        return collectorIds
    }

    private suspend fun importRemoteEvents(remoteText: String): ImportResult {
        val remote = JSONArray(remoteText)
        if (remote.length() == 0) return ImportResult(0, 0)

        val existing = repo.getAllCollectingEventsSync()
        val existingUuids = existing.map { it.event.uuid }.toHashSet()
        val existingByUuid = existing.associateBy { it.event.uuid }

        val collectors = repo.getAllCollectorsSync()
        val collectorMap = collectors.associateBy({ it.name.trim().lowercase() }, { it.id }).toMutableMap()

        val techniques = repo.getAllCollectionTechniquesSync()
        val techniqueSet = techniques.map { it.name.trim().lowercase() }.toHashSet()

        var inserted = 0
        var updated = 0

        for (i in 0 until remote.length()) {
            val obj = remote.optJSONObject(i) ?: continue
            val uuid = obj.optString("uuid").trim()
            if (uuid.isBlank()) continue

            val technique = if (obj.isNull("collectionTechnique")) null
            else obj.optString("collectionTechnique").trim().ifBlank { null }
            if (technique != null) {
                val key = technique.lowercase()
                if (!techniqueSet.contains(key)) {
                    repo.insertCollectionTechnique(technique)
                    techniqueSet.add(key)
                }
            }

            if (existingUuids.contains(uuid)) {
                val local = existingByUuid[uuid] ?: continue
                val remoteModified = if (obj.isNull("modifiedAt")) null
                    else obj.optString("modifiedAt").ifBlank { null }
                if (isRemoteNewer(remoteModified, local.event.modifiedAt)) {
                    val event = parseEventFromJson(obj, uuid, technique)
                    val collectorIds = resolveCollectorIds(obj, collectorMap)
                    repo.updateCollectingEvent(event, collectorIds)
                    updated++
                }
                continue
            }

            val event = parseEventFromJson(obj, uuid, technique)
            val collectorIds = resolveCollectorIds(obj, collectorMap)

            repo.insertCollectingEvent(event, collectorIds)
            inserted++
            existingUuids.add(uuid)
        }

        return ImportResult(inserted, updated)
    }

    private fun parseNullableDouble(obj: JSONObject, key: String): Double? {
        if (obj.isNull(key)) return null
        return when (val v = obj.opt(key)) {
            is Number -> v.toDouble()
            is String -> v.trim().toDoubleOrNull()
            else -> null
        }
    }

    private fun parseNullableInt(obj: JSONObject, key: String): Int? {
        if (obj.isNull(key)) return null
        return when (val v = obj.opt(key)) {
            is Number -> v.toInt()
            is String -> v.trim().toIntOrNull()
            else -> null
        }
    }

    private fun parseNullableFloat(obj: JSONObject, key: String): Float? {
        if (obj.isNull(key)) return null
        return when (val v = obj.opt(key)) {
            is Number -> v.toFloat()
            is String -> v.trim().toFloatOrNull()
            else -> null
        }
    }
}
