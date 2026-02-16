package com.spatium.fieldcollect.util

import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

object DateUtils {

    private val isoFormatter = DateTimeFormatter.ISO_INSTANT
    private val displayFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")

    fun nowIso(): String = Instant.now().toString()

    fun formatForDisplay(iso: String): String {
        return try {
            val instant = Instant.parse(iso)
            val local = LocalDateTime.ofInstant(instant, ZoneId.systemDefault())
            displayFormatter.format(local)
        } catch (e: Exception) {
            iso
        }
    }

    fun localDateTimeToIso(ldt: LocalDateTime): String {
        return ldt.atZone(ZoneId.systemDefault()).toInstant().toString()
    }

    fun isoToLocalDateTime(iso: String): LocalDateTime {
        val instant = Instant.parse(iso)
        return LocalDateTime.ofInstant(instant, ZoneId.systemDefault())
    }
}
