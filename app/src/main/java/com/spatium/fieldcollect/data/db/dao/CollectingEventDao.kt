package com.spatium.fieldcollect.data.db.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction
import androidx.room.Update
import com.spatium.fieldcollect.data.db.entity.CollectingEvent
import com.spatium.fieldcollect.data.db.entity.CollectingEventCollectorCrossRef
import com.spatium.fieldcollect.data.db.entity.CollectingEventWithCollectors
import kotlinx.coroutines.flow.Flow

@Dao
interface CollectingEventDao {

    @Transaction
    @Query("SELECT * FROM collecting_events ORDER BY createdAt DESC")
    fun getAllWithCollectors(): Flow<List<CollectingEventWithCollectors>>

    @Transaction
    @Query("SELECT * FROM collecting_events ORDER BY createdAt DESC")
    suspend fun getAllWithCollectorsSync(): List<CollectingEventWithCollectors>

    @Transaction
    @Query("SELECT * FROM collecting_events WHERE uuid = :uuid")
    suspend fun getByUuid(uuid: String): CollectingEventWithCollectors?

    @Insert
    suspend fun insert(event: CollectingEvent)

    @Update
    suspend fun update(event: CollectingEvent)

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insertCollectorRef(ref: CollectingEventCollectorCrossRef)

    @Query("DELETE FROM collecting_event_collector WHERE eventUuid = :uuid")
    suspend fun deleteCollectorRefs(uuid: String)

    @Query("DELETE FROM collecting_events WHERE uuid = :uuid")
    suspend fun delete(uuid: String)

    @Query("SELECT COUNT(*) FROM collecting_events")
    suspend fun count(): Int

    @Query("SELECT COUNT(*) FROM collecting_events WHERE collectionCode LIKE :prefix || '%'")
    suspend fun countByCodePrefix(prefix: String): Int
}
