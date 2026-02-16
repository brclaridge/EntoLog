package com.spatium.fieldcollect.data.db.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.spatium.fieldcollect.data.db.entity.TrapType
import kotlinx.coroutines.flow.Flow

@Dao
interface TrapTypeDao {

    @Query("SELECT * FROM trap_types ORDER BY name ASC")
    fun getAll(): Flow<List<TrapType>>

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(trapType: TrapType): Long
}
