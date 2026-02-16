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

    // Collection code generation: YYMMDD-NNN
    suspend fun generateCollectionCode(): String {
        val today = LocalDate.now()
        val prefix = today.format(DateTimeFormatter.ofPattern("yyMMdd"))
        val count = db.collectingEventDao().countByCodePrefix(prefix)
        val seq = count + 1
        return "$prefix-${seq.toString().padStart(3, '0')}"
    }

    // Collecting Events
    val collectingEvents: Flow<List<CollectingEventWithCollectors>> =
        db.collectingEventDao().getAllWithCollectors()

    suspend fun getAllCollectingEventsSync(): List<CollectingEventWithCollectors> =
        db.collectingEventDao().getAllWithCollectorsSync()

    suspend fun getByUuid(uuid: String): CollectingEventWithCollectors? =
        db.collectingEventDao().getByUuid(uuid)

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
        val newCode = generateCollectionCode()
        val newEvent = e.copy(
            uuid = newUuid,
            collectionCode = newCode,
            createdAt = java.time.Instant.now().toString(),
            modifiedAt = java.time.Instant.now().toString()
        )
        db.withTransaction {
            db.collectingEventDao().insert(newEvent)
            existing.collectors.forEach { c ->
                db.collectingEventDao().insertCollectorRef(
                    CollectingEventCollectorCrossRef(newUuid, c.id)
                )
            }
        }
        return newEvent
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
