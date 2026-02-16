package com.spatium.fieldcollect

import android.app.Application
import com.spatium.fieldcollect.data.db.AppDatabase

class FieldCollectApp : Application() {

    val database: AppDatabase by lazy {
        AppDatabase.getInstance(this)
    }
}
