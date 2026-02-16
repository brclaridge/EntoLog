package com.spatium.fieldcollect.ui.specimen

import android.Manifest
import android.app.DatePickerDialog
import android.app.TimePickerDialog
import android.net.Uri
import android.os.Bundle
import android.view.KeyEvent
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.EditText
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.lifecycleScope
import androidx.navigation.fragment.findNavController
import androidx.navigation.navOptions
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.spatium.fieldcollect.R
import com.spatium.fieldcollect.camera.CameraHelper
import com.spatium.fieldcollect.data.db.entity.CollectingEvent
import com.spatium.fieldcollect.data.db.entity.CollectionTechnique
import com.spatium.fieldcollect.data.db.entity.Collector
import com.spatium.fieldcollect.data.db.entity.Photo
import com.spatium.fieldcollect.databinding.FragmentSpecimenFormBinding
import com.spatium.fieldcollect.location.LocationHelper
import com.spatium.fieldcollect.util.DateUtils
import com.spatium.fieldcollect.viewmodel.CollectingEventViewModel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.time.LocalDateTime
import java.util.Calendar
import java.util.UUID

class SpecimenFormFragment : Fragment() {

    private var _binding: FragmentSpecimenFormBinding? = null
    private val binding get() = _binding!!

    private val viewModel: CollectingEventViewModel by viewModels()
    private lateinit var locationHelper: LocationHelper
    private lateinit var cameraHelper: CameraHelper

    private var lastGpsAccuracy: Float? = null
    private var eventDateTime: LocalDateTime = LocalDateTime.now()
    private var photoUri: Uri? = null
    private var collectionCode: String = ""
    private var existingPhotoCount: Int = 0
    private var coordPrecision: Int = 5

    private val isEditMode: Boolean by lazy { arguments?.getString("eventUuid") != null }
    private val recordUuid: String by lazy {
        arguments?.getString("eventUuid") ?: UUID.randomUUID().toString()
    }

    private val photoPaths: MutableList<String> = mutableListOf()

    private var allCollectors: List<Collector> = emptyList()
    private var allCollectionTechniques: List<CollectionTechnique> = emptyList()
    private val selectedCollectorIds: MutableSet<Long> = mutableSetOf()

    private val locationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        if (permissions[Manifest.permission.ACCESS_FINE_LOCATION] == true) {
            fetchLocation()
        }
    }

    private val cameraPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) launchCamera()
    }

    private val cameraLauncher = registerForActivityResult(
        ActivityResultContracts.TakePicture()
    ) { success ->
        if (success) {
            cameraHelper.getLastPhotoPath()?.let { path ->
                photoPaths.add(path)
                showPhotoPreview(path)
                updatePhotoButton()
            }
        }
    }

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View {
        _binding = FragmentSpecimenFormBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        locationHelper = LocationHelper(requireContext())
        cameraHelper = CameraHelper(requireContext())

        binding.btnEventDatetime.setOnClickListener { pickEventDateTime() }
        binding.btnFetchGps.setOnClickListener {
            locationPermissionLauncher.launch(
                arrayOf(
                    Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION
                )
            )
        }
        binding.btnRetryGeocode.setOnClickListener { retryReverseGeocode() }
        binding.btnSelectCollectors.setOnClickListener { showCollectorPicker() }
        binding.btnTakePhoto.setOnClickListener {
            cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
        binding.btnSave.setOnClickListener { saveRecord() }
        setupKeyboardShortcuts(view)

        binding.ddCollectionTechnique.setOnItemClickListener { _, _, position, _ ->
            val items = allCollectionTechniques.map { it.name } + "+ Add new technique..."
            if (position == items.size - 1) {
                binding.ddCollectionTechnique.setText("", false)
                showAddCollectionTechniqueDialog()
            }
        }

        // Coord precision dropdown
        val precisionItems = listOf("4", "5", "6")
        val precisionAdapter = ArrayAdapter(
            requireContext(),
            android.R.layout.simple_dropdown_item_1line,
            precisionItems
        )
        binding.ddCoordPrecision.setAdapter(precisionAdapter)
        binding.ddCoordPrecision.setText("5", false)
        binding.ddCoordPrecision.setOnItemClickListener { _, _, position, _ ->
            coordPrecision = precisionItems[position].toInt()
        }

        updateEventDateTimeButton()

        if (isEditMode) {
            loadExistingEvent()
        } else {
            viewLifecycleOwner.lifecycleScope.launch {
                collectionCode = viewModel.generateCode()
            }
            locationPermissionLauncher.launch(
                arrayOf(
                    Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION
                )
            )
            refreshCollectors()
            refreshCollectionTechniques()
        }
    }

    private fun pickEventDateTime() {
        val cal = Calendar.getInstance().apply {
            set(eventDateTime.year, eventDateTime.monthValue - 1, eventDateTime.dayOfMonth,
                eventDateTime.hour, eventDateTime.minute)
        }
        DatePickerDialog(
            requireContext(),
            { _, year, month, day ->
                TimePickerDialog(
                    requireContext(),
                    { _, hour, minute ->
                        eventDateTime = LocalDateTime.of(year, month + 1, day, hour, minute)
                        updateEventDateTimeButton()
                    },
                    cal.get(Calendar.HOUR_OF_DAY),
                    cal.get(Calendar.MINUTE),
                    true
                ).show()
            },
            cal.get(Calendar.YEAR),
            cal.get(Calendar.MONTH),
            cal.get(Calendar.DAY_OF_MONTH)
        ).show()
    }

    private fun updateEventDateTimeButton() {
        val iso = DateUtils.localDateTimeToIso(eventDateTime)
        binding.btnEventDatetime.text =
            "${getString(R.string.event_date)}: ${DateUtils.formatForDisplay(iso)}"
    }

    private fun loadExistingEvent() {
        viewLifecycleOwner.lifecycleScope.launch {
            val loaded = viewModel.getByUuid(recordUuid) ?: return@launch
            val e = loaded.event

            collectionCode = e.collectionCode

            // Parse createdAt into eventDateTime
            try {
                eventDateTime = DateUtils.isoToLocalDateTime(e.createdAt)
            } catch (_: Exception) {}
            updateEventDateTimeButton()

            // Pre-populate GPS fields
            if (e.latitude != null) {
                binding.etLatitude.setText(e.latitude.toString())
            }
            if (e.longitude != null) {
                binding.etLongitude.setText(e.longitude.toString())
            }
            if (e.elevation != null) {
                binding.etElevation.setText(e.elevation.toString())
            }
            lastGpsAccuracy = e.gpsAccuracy
            coordPrecision = e.coordPrecision
            binding.ddCoordPrecision.setText(coordPrecision.toString(), false)

            // Pre-populate fields
            binding.etCountry.setText(e.country)
            binding.etStateProvince.setText(e.stateProvince)
            binding.etCounty.setText(e.county)
            binding.etLocality.setText(e.locality)
            binding.etHost.setText(e.host)
            binding.etNotes.setText(e.notes)

            // Pre-populate collection technique dropdown
            allCollectionTechniques = viewModel.collectionTechniques.first()
            val techItems = allCollectionTechniques.map { it.name } + "+ Add new technique..."
            val techAdapter = ArrayAdapter(
                requireContext(),
                android.R.layout.simple_dropdown_item_1line,
                techItems
            )
            binding.ddCollectionTechnique.setAdapter(techAdapter)
            e.collectionTechnique?.let { binding.ddCollectionTechnique.setText(it, false) }

            // Pre-select collectors
            allCollectors = viewModel.collectors.first()
            selectedCollectorIds.addAll(loaded.collectors.map { it.id })
            updateCollectorButtonText()

            // Load existing photo count
            val photos = viewModel.getPhotos(recordUuid).first()
            existingPhotoCount = photos.size
            updatePhotoButton()

            // Show last existing photo as preview
            photos.lastOrNull()?.let { showPhotoPreview(it.filePath) }
        }
    }

    private fun refreshCollectors() {
        viewLifecycleOwner.lifecycleScope.launch {
            allCollectors = viewModel.collectors.first()
            updateCollectorButtonText()
        }
    }

    private fun refreshCollectionTechniques() {
        viewLifecycleOwner.lifecycleScope.launch {
            allCollectionTechniques = viewModel.collectionTechniques.first()
            val items = allCollectionTechniques.map { it.name } + "+ Add new technique..."
            val adapter = ArrayAdapter(
                requireContext(),
                android.R.layout.simple_dropdown_item_1line,
                items
            )
            binding.ddCollectionTechnique.setAdapter(adapter)
        }
    }

    private fun showAddCollectionTechniqueDialog() {
        val input = EditText(requireContext()).apply {
            hint = "Technique name"
            setPadding(48, 32, 48, 16)
        }
        MaterialAlertDialogBuilder(requireContext())
            .setTitle("Add Collection Technique")
            .setView(input)
            .setPositiveButton("Add") { _, _ ->
                val name = input.text.toString().trim()
                if (name.isNotEmpty()) {
                    viewLifecycleOwner.lifecycleScope.launch {
                        viewModel.addCollectionTechnique(name)
                        refreshCollectionTechniques()
                        binding.ddCollectionTechnique.setText(name, false)
                    }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun fetchLocation() {
        binding.btnFetchGps.text = getString(R.string.fetching_gps)
        viewLifecycleOwner.lifecycleScope.launch {
            val loc = locationHelper.getCurrentLocation()
            if (loc != null) {
                binding.etLatitude.setText(String.format("%.${coordPrecision}f", loc.latitude))
                binding.etLongitude.setText(String.format("%.${coordPrecision}f", loc.longitude))
                binding.etElevation.setText(loc.elevation.toInt().toString())
                lastGpsAccuracy = loc.accuracy
                binding.etCountry.setText(loc.country)
                binding.etStateProvince.setText(loc.stateProvince)
                binding.etCounty.setText(loc.county)
                binding.etLocality.setText(loc.locality)
                val geocodeMissing = loc.country.isBlank() &&
                    loc.stateProvince.isBlank() &&
                    loc.county.isBlank() &&
                    loc.locality.isBlank()
                binding.tvGeocodeStatus.visibility = if (geocodeMissing) View.VISIBLE else View.GONE
                binding.btnFetchGps.text = getString(R.string.fetch_gps)
            } else {
                binding.btnFetchGps.text = getString(R.string.fetch_gps)
                Toast.makeText(requireContext(), "GPS unavailable", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun retryReverseGeocode() {
        val lat = binding.etLatitude.text.toString().toDoubleOrNull()
        val lon = binding.etLongitude.text.toString().toDoubleOrNull()
        if (lat == null || lon == null) {
            Toast.makeText(requireContext(), "Enter latitude and longitude first", Toast.LENGTH_SHORT).show()
            return
        }
        viewLifecycleOwner.lifecycleScope.launch {
            val geo = locationHelper.reverseGeocode(lat, lon)
            if (geo.country.isNotBlank()) binding.etCountry.setText(geo.country)
            if (geo.stateProvince.isNotBlank()) binding.etStateProvince.setText(geo.stateProvince)
            if (geo.county.isNotBlank()) binding.etCounty.setText(geo.county)
            if (geo.locality.isNotBlank()) binding.etLocality.setText(geo.locality)
            val geocodeMissing = geo.country.isBlank() &&
                geo.stateProvince.isBlank() &&
                geo.county.isBlank() &&
                geo.locality.isBlank()
            binding.tvGeocodeStatus.visibility = if (geocodeMissing) View.VISIBLE else View.GONE
            Toast.makeText(requireContext(), "Locality lookup updated", Toast.LENGTH_SHORT).show()
        }
    }

    private fun launchCamera() {
        val (uri, _) = cameraHelper.createPhotoFile(recordUuid)
        photoUri = uri
        cameraLauncher.launch(uri)
    }

    private fun showPhotoPreview(path: String) {
        val bitmap = CameraHelper.loadBitmap(path, sampleSize = 4)
        binding.ivPhotoPreview.setImageBitmap(bitmap)
        binding.ivPhotoPreview.visibility = View.VISIBLE
    }

    private fun updatePhotoButton() {
        val total = existingPhotoCount + photoPaths.size
        binding.btnTakePhoto.text = if (total == 0) {
            getString(R.string.take_photo)
        } else {
            "$total photo(s) — tap for more"
        }
    }

    private fun showCollectorPicker() {
        val names = allCollectors.map { it.name }.toMutableList()
        names.add("+ Add new collector...")
        val checked = BooleanArray(names.size) { i ->
            if (i < allCollectors.size) selectedCollectorIds.contains(allCollectors[i].id)
            else false
        }

        MaterialAlertDialogBuilder(requireContext())
            .setTitle(R.string.collectors_label)
            .setMultiChoiceItems(names.toTypedArray(), checked) { dialog, which, isChecked ->
                if (which == names.size - 1 && isChecked) {
                    dialog.dismiss()
                    showAddCollectorDialog()
                    return@setMultiChoiceItems
                }
                if (which < allCollectors.size) {
                    val id = allCollectors[which].id
                    if (isChecked) selectedCollectorIds.add(id)
                    else selectedCollectorIds.remove(id)
                }
            }
            .setPositiveButton("OK") { _, _ -> updateCollectorButtonText() }
            .show()
    }

    private fun showAddCollectorDialog() {
        val input = EditText(requireContext()).apply {
            hint = "Collector name"
            setPadding(48, 32, 48, 16)
        }
        MaterialAlertDialogBuilder(requireContext())
            .setTitle("Add Collector")
            .setView(input)
            .setPositiveButton("Add") { _, _ ->
                val name = input.text.toString().trim()
                if (name.isNotEmpty()) {
                    viewLifecycleOwner.lifecycleScope.launch {
                        val newId = viewModel.addCollector(name)
                        if (newId > 0) selectedCollectorIds.add(newId)
                        refreshCollectors()
                    }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun updateCollectorButtonText() {
        val selectedNames = allCollectors
            .filter { selectedCollectorIds.contains(it.id) }
            .joinToString(", ") { it.name }
        binding.btnSelectCollectors.text = selectedNames.ifEmpty {
            getString(R.string.collectors_label)
        }
    }

    private fun setupKeyboardShortcuts(rootView: View) {
        rootView.setOnKeyListener { _, keyCode, event ->
            handleShortcutKeyEvent(keyCode, event)
        }
        if (rootView is ViewGroup) {
            attachShortcutKeyListeners(rootView)
        }
    }

    private fun attachShortcutKeyListeners(parent: ViewGroup) {
        for (i in 0 until parent.childCount) {
            val child = parent.getChildAt(i)
            child.setOnKeyListener { _, keyCode, event ->
                handleShortcutKeyEvent(keyCode, event)
            }
            if (child is ViewGroup) {
                attachShortcutKeyListeners(child)
            }
        }
    }

    private fun handleShortcutKeyEvent(keyCode: Int, event: KeyEvent): Boolean {
        if (event.action != KeyEvent.ACTION_DOWN || event.repeatCount > 0) {
            return false
        }
        return when {
            keyCode == KeyEvent.KEYCODE_S && event.isCtrlPressed -> {
                saveRecord(returnToTableView = true)
                true
            }
            keyCode == KeyEvent.KEYCODE_ESCAPE -> {
                cancelAndReturnToTableView()
                true
            }
            else -> false
        }
    }

    private fun cancelAndReturnToTableView() {
        navigateToRecordsTableView()
    }

    private fun navigateToRecordsTableView() {
        val navController = findNavController()
        if (!navController.popBackStack(R.id.recordsListFragment, false)) {
            navController.navigate(
                R.id.recordsListFragment,
                null,
                navOptions {
                    popUpTo(navController.currentDestination?.id ?: return@navOptions) {
                        inclusive = true
                    }
                }
            )
        }
    }

    private fun saveRecord(returnToTableView: Boolean = false) {
        val technique = binding.ddCollectionTechnique.text.toString().let {
            if (it.isBlank()) null else it
        }

        val lat = binding.etLatitude.text.toString().toDoubleOrNull()
        val lon = binding.etLongitude.text.toString().toDoubleOrNull()
        val alt = binding.etElevation.text.toString().toIntOrNull()
        val accuracy = if (lat != null && lon != null) lastGpsAccuracy else null

        val event = CollectingEvent(
            uuid = recordUuid,
            collectionCode = collectionCode,
            latitude = lat,
            longitude = lon,
            elevation = alt,
            gpsAccuracy = accuracy,
            createdAt = DateUtils.localDateTimeToIso(eventDateTime),
            country = binding.etCountry.text.toString(),
            stateProvince = binding.etStateProvince.text.toString(),
            county = binding.etCounty.text.toString(),
            locality = binding.etLocality.text.toString(),
            host = binding.etHost.text.toString(),
            collectionTechnique = technique,
            notes = binding.etNotes.text.toString(),
            coordPrecision = coordPrecision,
            modifiedAt = java.time.Instant.now().toString()
        )

        viewLifecycleOwner.lifecycleScope.launch {
            if (isEditMode) {
                viewModel.update(event, selectedCollectorIds.toList())
            } else {
                viewModel.insert(event, selectedCollectorIds.toList())
            }
            // Save only new photos
            for (path in photoPaths) {
                viewModel.addPhoto(
                    Photo(
                        recordUuid = recordUuid,
                        filePath = path,
                        createdAt = DateUtils.nowIso()
                    )
                )
            }
            Toast.makeText(requireContext(), R.string.saved, Toast.LENGTH_SHORT).show()
            if (returnToTableView) {
                navigateToRecordsTableView()
            } else {
                findNavController().popBackStack()
            }
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}
