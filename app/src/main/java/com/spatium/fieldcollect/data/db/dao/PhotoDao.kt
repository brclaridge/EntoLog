package com.spatium.fieldcollect.data.db.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query
import com.spatium.fieldcollect.data.db.entity.Photo
import kotlinx.coroutines.flow.Flow

@Dao
interface PhotoDao {

    @Query("SELECT * FROM photos WHERE recordUuid = :recordUuid ORDER BY createdAt ASC")
    fun getForRecord(recordUuid: String): Flow<List<Photo>>

    @Query("SELECT * FROM photos WHERE recordUuid = :recordUuid ORDER BY createdAt ASC")
    suspend fun getForRecordSync(recordUuid: String): List<Photo>

    @Query("SELECT * FROM photos ORDER BY createdAt ASC")
    suspend fun getAllSync(): List<Photo>

    @Insert
    suspend fun insert(photo: Photo): Long

    @Query("DELETE FROM photos WHERE recordUuid = :recordUuid")
    suspend fun deleteForRecord(recordUuid: String)
}
