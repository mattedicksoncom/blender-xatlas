/*
MIT License

Copyright (c) 2018-2020 Jonathan Young

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <time.h>
#include <iostream>

#include <thread>
#include <chrono>

#include <sstream>

#include <stb_image_write.h>

#ifdef _MSC_VER
#pragma warning(push)
#pragma warning(disable : 4201)
#endif
#include <tiny_obj_loader.h>
#ifdef _MSC_VER
#pragma warning(pop)
#endif

#include "../xatlas.h"

#ifdef _MSC_VER
#define FOPEN(_file, _filename, _mode) { if (fopen_s(&_file, _filename, _mode) != 0) _file = NULL; }
#define STRICMP _stricmp
#else
#define FOPEN(_file, _filename, _mode) _file = fopen(_filename, _mode)
#include <strings.h>
#define STRICMP strcasecmp
#endif

static bool s_verbose = false;

class Stopwatch
{
public:
	Stopwatch() { reset(); }
	void reset() { m_start = clock(); }
	double elapsed() const { return (clock() - m_start) * 1000.0 / CLOCKS_PER_SEC; }
private:
	clock_t m_start;
};

static int Print(const char *format, ...)
{
	va_list arg;
	va_start(arg, format);
	printf("\r"); // Clear progress text (PrintProgress).
	const int result = vprintf(format, arg);
	va_end(arg);
	return result;
}

static void PrintProgress(const char *name, const char *indent1, const char *indent2, int progress, Stopwatch *stopwatch)
{
	if (s_verbose)
		return;
	if (progress == 0)
		stopwatch->reset();
	printf("\r%s%s [", indent1, name);
	for (int i = 0; i < 10; i++)
		printf(progress / ((i + 1) * 10) ? "*" : " ");
	printf("] %d%%", progress);
	fflush(stdout);
	if (progress == 100)
		printf("\n%s%.2f seconds (%g ms) elapsed\n", indent2, stopwatch->elapsed() / 1000.0, stopwatch->elapsed());
}

static bool ProgressCallback(xatlas::ProgressCategory::Enum category, int progress, void *userData)
{
	Stopwatch *stopwatch = (Stopwatch *)userData;
	PrintProgress(xatlas::StringForEnum(category), "   ", "      ", progress, stopwatch);
	return true;
}

static bool checkArgumentInt(char *argv[], int index, char *comp_arg) {
	if (STRICMP(argv[index], comp_arg) == 0) {
		std::string resolutionAmount = argv[index + 1];
		std::istringstream iss(resolutionAmount);
		int val;
		if (iss >> val) {
			return true;
		}else {
			return false;
		}
	}
	return false;
}

static bool checkArgumentFloat(char *argv[], int index, char *comp_arg) {
	if (STRICMP(argv[index], comp_arg) == 0) {
		std::string resolutionAmount = argv[index + 1];
		std::istringstream iss(resolutionAmount);
		float val;
		if (iss >> val) {
			return true;
		}
		else {
			return false;
		}
	}
	return false;
}

//static void fakePrintf(std::string printString, ) {
//	std::string printCode = (std::string)0;
//	printCode.append(printString);
//	printf(printCode, );
//}

int main(int argc, char *argv[])
{
	std::string meshInput;
	std::string line;

	//read all the mesh input
	while (std::getline(std::cin, line) && !line.empty()) {
		meshInput.append(line);
		meshInput.append("\n");
	}

	//printf("Loading '%s'...\n", argv[1]);
	printf("Loading Mesh from stdin...\n");
	std::vector<tinyobj::shape_t> shapes;
	std::vector<tinyobj::material_t> materials;
	std::vector<tinyobj::MaterialReader> matReader;
	std::string err;

	if (!tinyobj::LoadObj(
			shapes,
			materials,
			err,
			meshInput,
			tinyobj::triangulation
	)) {
		printf("Error: %s\n", err.c_str());
		return EXIT_FAILURE;
	}

	//print the amount of shapes if working
	//std::cout << (int)shapes.size() << std::endl;

	//std::cout << "exit" << std::endl;

	if (argc < 1) {
	    printf("Usage: %s input_file.obj [options]\n", argv[0]);
		printf("  Options:\n");
		printf("    -verbose\n");  
		printf("    -resolution\n");
	    return 1;
	}
	//printf("Running xatlas\n");
	// compare arg2 with -verbose
	s_verbose = (argc >= 3 && STRICMP(argv[2], "-verbose") == 0);

	//settings
	//printf("Settings\n");
	xatlas::ChartOptions chartOptions;
	xatlas::PackOptions packOptions;
	enum class AtlasLayout { overlap, spreadX, udim };
	AtlasLayout atlasLayout = AtlasLayout::overlap;
	bool packOnly = false;


	//printf("Before check\n");
	//check all the arguments
	if (argc >= 2) {
		for (int counter = 2; counter < argc; counter++) {
			//shared options-------------------------------------
			//atlasLayout
			if (STRICMP(argv[counter], "-atlasLayout") == 0) {
				if (STRICMP(argv[counter + 1], "OVERLAP")) {
					atlasLayout = AtlasLayout::overlap;
				}
				if (STRICMP(argv[counter + 1], "SPREADX") == 0) {
					atlasLayout = AtlasLayout::spreadX;
				}
				if (STRICMP(argv[counter + 1], "UDIM") == 0) {
					atlasLayout = AtlasLayout::udim;
				}
			}
			//pack only
			if (STRICMP(argv[counter], "-packOnly") == 0) {
				packOnly = true;
			}

			//pack options-------------------------------------
			//resolution
			if (checkArgumentInt(argv, counter, "-resolution")) {
				packOptions.resolution = atoi(argv[counter + 1]);
			}
			//padding
			if (checkArgumentInt(argv, counter, "-padding")) {
				packOptions.padding = atoi(argv[counter + 1]);
			}
			//brute force
			if (STRICMP(argv[counter], "-bruteForce") == 0) {
				packOptions.bruteForce = true;
			}
			//bilinear
			if (STRICMP(argv[counter], "-bilinear") == 0) {
				packOptions.bilinear = true;
			}
			//blockAlign
			if (STRICMP(argv[counter], "-blockAlign") == 0) {
				packOptions.blockAlign = true;
			}
			//maxChartSize
			if (checkArgumentInt(argv, counter, "-maxChartSize")) {
				packOptions.maxChartSize = atoi(argv[counter + 1]);
			}
			//texelsPerUnit
			if (checkArgumentFloat(argv, counter, "-texelsPerUnit")) {
				packOptions.texelsPerUnit = std::stof(argv[counter + 1]);
			}

			//chart options-------------------------------------
			//maxChartArea
			if (checkArgumentFloat(argv, counter, "-maxChartArea")) {
				chartOptions.maxChartArea = std::stof(argv[counter + 1]);
			}
			//maxBoundaryLength
			if (checkArgumentFloat(argv, counter, "-maxBoundaryLength")) {
				chartOptions.maxBoundaryLength = std::stof(argv[counter + 1]);
			}
			//normalDeviationWeight
			if (checkArgumentFloat(argv, counter, "-normalDeviationWeight")) {
				chartOptions.normalDeviationWeight = std::stof(argv[counter + 1]);
			}
			//roundnessWeight
			if (checkArgumentFloat(argv, counter, "-roundnessWeight")) {
				chartOptions.roundnessWeight = std::stof(argv[counter + 1]);
			}
			//straightnessWeight
			if (checkArgumentFloat(argv, counter, "-straightnessWeight")) {
				chartOptions.straightnessWeight = std::stof(argv[counter + 1]);
			}
			//normalSeamWeight
			if (checkArgumentFloat(argv, counter, "-normalSeamWeight")) {
				chartOptions.normalSeamWeight = std::stof(argv[counter + 1]);
			}
			//textureSeamWeight
			if (checkArgumentFloat(argv, counter, "-textureSeamWeight")) {
				chartOptions.textureSeamWeight = std::stof(argv[counter + 1]);
			}
			//maxCost
			if (checkArgumentFloat(argv, counter, "-maxCost")) {
				chartOptions.maxCost = std::stof(argv[counter + 1]);
			}
			//maxIterations
			if (checkArgumentInt(argv, counter, "-maxIterations")) {
				chartOptions.maxIterations = atoi(argv[counter + 1]);
			}
		}
	}

	

	// Load object file.
	if (shapes.size() == 0) {
		printf("Error: no shapes in obj file\n");
		return EXIT_FAILURE;
	}
	printf("   %d shapes\n", (int)shapes.size());
	// Create empty atlas.
	xatlas::SetPrint(Print, s_verbose);
	xatlas::Atlas *atlas = xatlas::Create();
	//atlas.height = packOptions.resolution;
	//atlas.width = packOptions.resolution;
	// Set progress callback.
	Stopwatch globalStopwatch, stopwatch;
	xatlas::SetProgressCallback(atlas, ProgressCallback, &stopwatch);
	// Add meshes to atlas.
	uint32_t totalVertices = 0, totalFaces = 0;
	if (packOnly) {
		for (int i = 0; i < (int)shapes.size(); i++) {
			const tinyobj::mesh_t &objMesh = shapes[i].mesh;
			//xatlas::MeshDecl meshDecl;
			xatlas::UvMeshDecl meshDecl;
			meshDecl.vertexCount = (uint32_t)objMesh.positions.size() / 3;
			meshDecl.vertexPositionData = objMesh.positions.data();
			meshDecl.vertexPositionStride = sizeof(float) * 3;
			// don't provide normal data i
			/*if (!objMesh.normals.empty()) {
				meshDecl.vertexNormalData = objMesh.normals.data();
				meshDecl.vertexNormalStride = sizeof(float) * 3;
			}*/
			if (!objMesh.texcoords.empty()) {
				meshDecl.vertexUvData = objMesh.texcoords.data();
				meshDecl.vertexUvStride = sizeof(float) * 2;
			}
			meshDecl.indexCount = (uint32_t)objMesh.indices.size();
			meshDecl.indexData = objMesh.indices.data();
			meshDecl.indexFormat = xatlas::IndexFormat::UInt32;
			//xatlas::AddMeshError::Enum error = xatlas::AddMesh(atlas, meshDecl, (uint32_t)shapes.size());
			xatlas::AddMeshError::Enum error = xatlas::AddUvMesh(atlas, meshDecl);
			if (error != xatlas::AddMeshError::Success) {
				xatlas::Destroy(atlas);
				printf("\rError adding mesh %d '%s': %s\n", i, shapes[i].name.c_str(), xatlas::StringForEnum(error));
				return EXIT_FAILURE;
			}
			totalVertices += meshDecl.vertexCount;
			totalFaces += meshDecl.indexCount / 3;
		}
	}
	else {
		for (int i = 0; i < (int)shapes.size(); i++) {
			const tinyobj::mesh_t &objMesh = shapes[i].mesh;
			xatlas::MeshDecl meshDecl;
			//xatlas::UvMeshDecl meshDecl;
			meshDecl.vertexCount = (uint32_t)objMesh.positions.size() / 3;
			meshDecl.vertexPositionData = objMesh.positions.data();
			meshDecl.vertexPositionStride = sizeof(float) * 3;
			// don't provide normal data i
			if (!objMesh.normals.empty()) {
				meshDecl.vertexNormalData = objMesh.normals.data();
				meshDecl.vertexNormalStride = sizeof(float) * 3;
			}
			if (!objMesh.texcoords.empty()) {
				meshDecl.vertexUvData = objMesh.texcoords.data();
				meshDecl.vertexUvStride = sizeof(float) * 2;
			}
			meshDecl.indexCount = (uint32_t)objMesh.indices.size();
			meshDecl.indexData = objMesh.indices.data();
			meshDecl.indexFormat = xatlas::IndexFormat::UInt32;
			xatlas::AddMeshError::Enum error = xatlas::AddMesh(atlas, meshDecl, (uint32_t)shapes.size());
			//xatlas::AddMeshError::Enum error = xatlas::AddUvMesh(atlas, meshDecl);
			if (error != xatlas::AddMeshError::Success) {
				xatlas::Destroy(atlas);
				printf("\rError adding mesh %d '%s': %s\n", i, shapes[i].name.c_str(), xatlas::StringForEnum(error));
				return EXIT_FAILURE;
			}
			totalVertices += meshDecl.vertexCount;
			totalFaces += meshDecl.indexCount / 3;
		}
	}
	xatlas::AddMeshJoin(atlas); // Not necessary. Only called here so geometry totals are printed after the AddMesh progress indicator.
	printf("   %u total vertices\n", totalVertices);
	printf("   %u total triangles\n", totalFaces);
	// Generate atlas.
	printf("Generating atlas\n");

	
	xatlas::Generate(atlas, chartOptions, packOptions);
	printf("   %i pack res\n", packOptions.resolution);

	printf("   %d charts\n", atlas->chartCount);
	printf("   %d atlases\n", atlas->atlasCount);
	for (uint32_t i = 0; i < atlas->atlasCount; i++)
		printf("      %d: %0.2f%% utilization\n", i, atlas->utilization[i] * 100.0f);
	printf("   %ux%u resolution\n", atlas->width, atlas->height);
	totalVertices = totalFaces = 0;
	for (uint32_t i = 0; i < atlas->meshCount; i++) {
		const xatlas::Mesh &mesh = atlas->meshes[i];
		totalVertices += mesh.vertexCount;
		totalFaces += mesh.indexCount / 3;
	}
	printf("   %u total vertices\n", totalVertices);
	printf("   %u total triangles\n", totalFaces);
	printf("%.2f seconds (%g ms) elapsed total\n", globalStopwatch.elapsed() / 1000.0, globalStopwatch.elapsed());

	// Write meshes.
	printf("STARTOBJ\n");
	uint32_t firstVertex = 0;
	for (uint32_t i = 0; i < atlas->meshCount; i++) {
		const xatlas::Mesh &mesh = atlas->meshes[i];
		printf("o %s\n", shapes[i].name.c_str());
		//printf("cc %i\n", mesh.chartCount);
		printf("s off\n");
		for (uint32_t v = 0; v < mesh.vertexCount; v++) {
			const xatlas::Vertex &vertex = mesh.vertexArray[v];

			float xOffset = 0;
			float yOffset = 0;
			//spread the uv axis along the x-axis
			if (vertex.atlasIndex > 0 && atlasLayout == AtlasLayout::spreadX) {
				xOffset = (float)vertex.atlasIndex;
			}
			if (vertex.atlasIndex > 0 && atlasLayout == AtlasLayout::udim) {
				int xRowOffset = vertex.atlasIndex % 10;
				xOffset = (float)xRowOffset;
				yOffset = (float)floor(vertex.atlasIndex / 10);
			}

			const float *pos = &shapes[i].mesh.positions[vertex.xref * 3];
			//printf("v %g %g %g\n", pos[0], pos[1], pos[2]);
			if (!shapes[i].mesh.normals.empty()) {
				const float *normal = &shapes[i].mesh.normals[vertex.xref * 3];
				//printf("vn %g %g %g\n", normal[0], normal[1], normal[2]);
			}
			printf("vt %g %g\n", (vertex.uv[0] / atlas->width) + xOffset, (vertex.uv[1] / atlas->height) + yOffset);
		}
			
		for (uint32_t f = 0; f < mesh.indexCount; f += 3) {
			printf("f ");
			for (uint32_t j = 0; j < 3; j++) {
				const uint32_t index = firstVertex + mesh.indexArray[f + j] + 1; // 1-indexed
				printf("%d/%d/%d%c", index, index, index, j == 2 ? '\n' : ' ');
			}
		}
		firstVertex += mesh.vertexCount;
	}


	// Cleanup.
	xatlas::Destroy(atlas);
	printf("Done\n");

	//flush the output
	std::cout.flush();

	return EXIT_SUCCESS;
}
