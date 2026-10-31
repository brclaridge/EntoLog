package com.spatium.fieldcollect.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import com.spatium.fieldcollect.FieldCollectApp
import com.spatium.fieldcollect.data.db.entity.CollectionTechnique
import com.spatium.fieldcollect.data.db.entity.CollectingEvent
import com.spatium.fieldcollect.data.db.entity.CollectingEventWithCollectors
import com.spatium.fieldcollect.data.db.entity.Photo
import com.spatium.fieldcollect.data.repository.FieldRepository
import kotlinx.coroutines.flow.Flow

class CollectingEventViewModel(application: Application) : AndroidViewModel(application) {

    private val repo = FieldRepository((application as FieldCollectApp).database)

    val collectingEvents: Flow<List<CollectingEventWithCollectors>> = repo.collectingEvents
    val collectors = repo.collectors
    val collectionTechniques: Flow<List<CollectionTechnique>> = repo.collectionTechniques

    /** Saves a newly created record; the collection code is assigned on insert. */
    suspend fun insertNew(event: CollectingEvent, collectorIds: List<Long>): String =
        repo.insertNewCollectingEvent(event, collectorIds)

    suspend fun update(event: CollectingEvent, collectorIds: List<Long>) {
        repo.updateCollectingEvent(event, collectorIds)
    }

    suspend fun getByUuid(uuid: String): CollectingEventWithCollectors? =
        repo.getByUuid(uuid)

    suspend fun duplicate(uuid: String): CollectingEvent? =
        repo.duplicateCollectingEvent(uuid)

    suspend fun delete(uuid: String) {
        repo.deleteCollectingEvent(uuid)
    }

    suspend fun addCollector(name: String): Long = repo.insertCollector(name)
    suspend fun addCollectionTechnique(name: String): Long = repo.insertCollectionTechnique(name)

    fun getPhotos(recordUuid: String): Flow<List<Photo>> = repo.getPhotosForRecord(recordUuid)
    suspend fun addPhoto(photo: Photo): Long = repo.insertPhoto(photo)
}
