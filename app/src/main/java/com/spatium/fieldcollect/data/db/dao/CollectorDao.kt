package com.spatium.fieldcollect.data.db.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.spatium.fieldcollect.data.db.entity.Collector
import kotlinx.coroutines.flow.Flow

@Dao
interface CollectorDao {

    @Query("SELECT * FROM collectors ORDER BY name ASC")
    fun getAll(): Flow<List<Collector>>

    @Query("SELECT * FROM collectors ORDER BY name ASC")
    suspend fun getAllSync(): List<Collector>

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(collector: Collector): Long

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insertAll(collectors: List<Collector>)

    @Query("SELECT COUNT(*) FROM collectors")
    suspend fun count(): Int
}
