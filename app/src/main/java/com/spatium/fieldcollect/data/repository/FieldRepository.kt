package com.spatium.fieldcollect.data.repository

import androidx.room.withTransaction
import com.spatium.fieldcollect.data.db.AppDatabase
import com.spatium.fieldcollect.data.db.entity.CollectionTechnique
import com.spatium.fieldcollect.data.db.entity.Collector
import com.spatium.fieldcollect.data.db.entity.CollectingEvent
import com.spatium.fieldcollect.data.db.entity.CollectingEventCollectorCrossRef
import com.spatium.fieldcollect.data.db.entity.CollectingEventWithCollectors
import com.spatium.fieldcollect.data.db.entity.Photo
import kotlinx.coroutines.flow.Flow
import java.time.LocalDate
import java.time.format.DateTimeFormatter

class FieldRepository(private val db: AppDatabase) {

    // Collectors
    val collectors: Flow<List<Collector>> = db.collectorDao().getAll()
    suspend fun getAllCollectorsSync(): List<Collector> = db.collectorDao().getAllSync()
    suspend fun insertCollector(name: String): Long =
        db.collectorDao().insert(Collector(name = name))

    // Collection Techniques
    val collectionTechniques: Flow<List<CollectionTechnique>> =
        db.collectionTechniqueDao().getAll()
    suspend fun getAllCollectionTechniquesSync(): List<CollectionTechnique> =
        db.collectionTechniqueDao().getAllSync()
    suspend fun insertCollectionTechnique(name: String): Long =
        db.collectionTechniqueDao().insert(CollectionTechnique(name = name))

    /**
     * Next unused accession code, as YYMMDD-NNN. Numbers are never reused, so
     * gaps left by deleted records are expected and correct.
     *
     * Call this inside the same transaction as the insert that consumes the
     * code — reading the maximum and writing the row have to be atomic or two
     * records can be handed the same number.
     */
    private suspend fun nextCollectionCode(): String {
        val prefix = LocalDate.now().format(DateTimeFormatter.ofPattern("yyMMdd"))
        var seq = (db.collectingEventDao().maxSeqForPrefix(prefix) ?: 0) + 1
        // MAX only sees codes shaped like the ones this generates. Codes typed by
        // hand on the desktop may collide without ever having been counted, so
        // confirm the candidate is actually free before handing it out.
        while (db.collectingEventDao().countByCode(formatCode(prefix, seq)) > 0) {
            seq++
        }
        return formatCode(prefix, seq)
    }

    private fun formatCode(prefix: String, seq: Int): String =
        "$prefix-${seq.toString().padStart(3, '0')}"

    // Collecting Events
    val collectingEvents: Flow<List<CollectingEventWithCollectors>> =
        db.collectingEventDao().getAllWithCollectors()

    suspend fun getAllCollectingEventsSync(): List<CollectingEventWithCollectors> =
        db.collectingEventDao().getAllWithCollectorsSync()

    suspend fun getByUuid(uuid: String): CollectingEventWithCollectors? =
        db.collectingEventDao().getByUuid(uuid)

    /**
     * Inserts a record created on this device, assigning it the next accession
     * code. Returns the code that was assigned.
     */
    suspend fun insertNewCollectingEvent(
        event: CollectingEvent,
        collectorIds: List<Long>
    ): String = db.withTransaction {
        val code = nextCollectionCode()
        db.collectingEventDao().insert(event.copy(collectionCode = code))
        collectorIds.forEach { cid ->
            db.collectingEventDao().insertCollectorRef(
                CollectingEventCollectorCrossRef(event.uuid, cid)
            )
        }
        code
    }

    /**
     * Inserts a record received from the desktop, preserving its collection code
     * verbatim — including a blank one, which is how desktop-entered historical
     * records arrive. Never assigns a code of its own.
     */
    suspend fun insertCollectingEvent(event: CollectingEvent, collectorIds: List<Long>) {
        db.withTransaction {
            db.collectingEventDao().insert(event)
            collectorIds.forEach { cid ->
                db.collectingEventDao().insertCollectorRef(
                    CollectingEventCollectorCrossRef(event.uuid, cid)
                )
            }
        }
    }

    suspend fun updateCollectingEvent(event: CollectingEvent, collectorIds: List<Long>) {
        db.withTransaction {
            db.collectingEventDao().update(event)
            db.collectingEventDao().deleteCollectorRefs(event.uuid)
            collectorIds.forEach { cid ->
                db.collectingEventDao().insertCollectorRef(
                    CollectingEventCollectorCrossRef(event.uuid, cid)
                )
            }
        }
    }

    suspend fun duplicateCollectingEvent(uuid: String): CollectingEvent? {
        val existing = db.collectingEventDao().getByUuid(uuid) ?: return null
        val e = existing.event
        val newUuid = java.util.UUID.randomUUID().toString()
        val now = java.time.Instant.now().toString()
        return db.withTransaction {
            val newEvent = e.copy(
                uuid = newUuid,
                collectionCode = nextCollectionCode(),
                createdAt = now,
                modifiedAt = now
            )
            db.collectingEventDao().insert(newEvent)
            existing.collectors.forEach { c ->
                db.collectingEventDao().insertCollectorRef(
                    CollectingEventCollectorCrossRef(newUuid, c.id)
                )
            }
            newEvent
        }
    }

    suspend fun deleteCollectingEvent(uuid: String) {
        db.photoDao().deleteForRecord(uuid)
        db.collectingEventDao().delete(uuid)
    }

    // Photos
    fun getPhotosForRecord(recordUuid: String): Flow<List<Photo>> =
        db.photoDao().getForRecord(recordUuid)

    suspend fun getPhotosForRecordSync(recordUuid: String): List<Photo> =
        db.photoDao().getForRecordSync(recordUuid)

    suspend fun getAllPhotosSync(): List<Photo> =
        db.photoDao().getAllSync()

    suspend fun insertPhoto(photo: Photo): Long =
        db.photoDao().insert(photo)
}
