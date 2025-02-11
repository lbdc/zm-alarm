<?php
//
// Login using api
//
$token_json = shell_exec('curl -k -XPOST -d "user=admin&pass=password" https://localhost/zm/api/host/login.json');
$token = (json_decode($token_json, true));
//
// Load cameras from database
//
$camera=Load_Camera();
//
// PHP Functions
//
function Load_Camera()
{
	// Read from etc/zm/zm.conf (ubuntu) or etc/zm.conf (centos)
	//
	if(file_exists("/etc/zm/zm.conf")) {
		$ini_file='/etc/zm/zm.conf';}
	else if(file_exists("/etc/zm.conf")) {
		$ini_file='/etc/zm.conf';}
	else { echo "No zoneminder configuration zm.conf found";}
	//
	// Parse ini file the long way (PHP deprecated # as comments in ini files)
	//
	$file = fopen($ini_file, "r");
	while(!feof($file)) {
		$line = fgets($file);
		if($line[0] =="#" || strlen($line) <=1) {
			// skip line
		}
		else {
			$config_ini=explode("=", $line);
			$config[$config_ini[0]]=str_replace(PHP_EOL, null, $config_ini[1]);
		}
	}
	fclose($file);
	define('ZM_HOST', $config['ZM_DB_HOST']);
	define('ZMUSER', $config['ZM_DB_USER']);
	define('ZMPASS', $config['ZM_DB_PASS']);
	define('ZM_DB', $config['ZM_DB_NAME']);	
	//
	// Loads cameras and event range
	//	
	$con=mysqli_connect(ZM_HOST,ZMUSER, ZMPASS, ZM_DB);
	if (mysqli_connect_errno()) {
		echo "Failed to connect to MySQL: " . mysqli_connect_error();
	}
	//
	// The SQL query
	//
	$result = mysqli_query($con,"SELECT Id, Name from Monitors, Monitor_Status WHERE Monitors.Id=Monitor_Status.MonitorId AND Function != 'None'");
	while($row = mysqli_fetch_assoc($result)) {
		$mon_name[]=$row;
	}
	// Add link and source placeholder
	$i=0;
	foreach($mon_name as &$name) {
		$name['Id'] = $mon_name[$i]['Id'];
		$name['Name'] = $mon_name[$i]['Name'];
		// add link and source of images
		$name['Link'] = "";
		$name['Source'] = "";
		$name['Value'] = "on";
		$i++;
 	}	
	mysqli_close($con);
	return $mon_name;
}
?>

<!DOCTYPE html>
<html lang="en">
<head>
	<meta charset="UTF-8">
	<meta http-equiv="refresh" content="300">
	<meta name="viewport" content="width=device-width, initial-scale=1.0">
	<style>
		.picture-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(600px, 1fr));
		gap: 2px;
		}

		.grid-item {
		border: 1px solid #ccc;
		position: relative;
		text-align: center;
		border-radius: 4px;
		box-shadow: 0 4px 4px rgba(0, 0, 0, 0.1);
		}

		.grid-item img {
		width: 100%;
		height: 100%;
		object-fit: contain;
		background-color: #000000;
		color: #4CAF50;
		}
		
	/* Define the default button style */
	.myButton {
		background-color: #4CAF50; /* Green */
		color: white;
		padding: 2px 4px;
		text-align: center;
		text-decoration: none;
		display: inline-block;
		font-size: 10px;
		margin: 2px 1px;
		cursor: pointer;
	}
	.myButtonClicked {
		background-color: #e7e7e7; 
		color: black;
		
	}
	.draggable {
		padding: 2px 4px;
		margin: 1px;
		border: 1px solid #ccc;
		cursor: grab;
	}
	.drop-target {
		background-color: #f0f0f0;
	}
	.over {
		border: 2px dashed #333;
	}
	 /* Style for the overlay button */
	.overlay-button {
		position: absolute;
		top: 50%;
		right: 1%;
		transform: translateY(-50%);
		background-color: rgba(52, 152, 219, 0.8); /* Semi-transparent blue */
		color: #fff;
		border: none;
		border-radius: 5px;
		cursor: pointer;
		opacity: 0.5; /* Initially hidden */
		transition: opacity 0.3s ease-in-out;
	}
	
	.non-draggable {
    opacity: 0.1; /* Example: reduce opacity for non-draggable buttons */
    cursor: not-allowed !important; /* Example: change cursor to indicate non-draggable state */
    /* Add any other styling as needed */
}

	</style>
	<title>ZM Montage</title>
</head>
<body>
	<!-- Containers to hold the top row buttons -->
	<div id="buttonLayout"></div>
		<button id="minus" class="myButton" onclick="resizeGrid('minus')">-</button><button id="size" class="myButton">Size:400</button><button id="plus" class="myButton" onclick="resizeGrid('plus')">+</button>
		<button id="scaledown" class="myButton" onclick="scaleimg('scaledown')">-</button><button id="scalenum" class="myButton">Scale:50%</button><button id="scaleup" class="myButton" onclick="scaleimg('scaleup')">+</button>
		<button id="save" class="myButton" onclick="saveToCookie()">save</button><button id="load" class="myButton" onclick="getFromCookie()">load</button><button id="reset" class="myButton" onclick="deleteCookie()">Reset</button>
	<div id="buttonContainer"></div>
	<!-- Container to hold the camera images -->
	<div class="picture-grid" id="pictureGrid"></div>
	<!-- Images will be added dynamically using JavaScript -->
<script>   
	//
	// Initialize variables from zoneminder to load cameras from zm database
	//
	var token="<?php echo $token["access_token"]; ?>";
	var camera =<?php echo json_encode($camera); ?>;
	const pictureGrid = document.getElementById('pictureGrid'); // this doesnt seem required here
	let size = 400; // Initial size
	let scale = 50; // Initial scale
	// Get the container element
	var buttonContainer = document.getElementById("buttonContainer");
	// Call createButton() to create button grid
	createButton();
	// Call createGrid() initially to create the img grid
	createGrid();
	// Load last page saved on open
	getFromCookie();
	// Set up a timer to update the images every 1 seconds (adjust as needed)
	setInterval(updateImageSrc, 1000);
//
// FUNCTIONS
//
// Function to check and display the state of a button
function toggleButtonState(buttonId) {
	var button = document.getElementById(buttonId);
	var gridItems = document.getElementById("grid_" + buttonId);
	if (button.value == "on") {
		button.classList.add('myButtonClicked');
		button.value = "off";
		gridItems.style.display = "none"; // Hide the div
		for (var i = 0; i < camera.length; i++) {
			if (camera[i].Id === buttonId) {
				camera[i].Value = "off";
				break; // Once the update is done, exit the loop
			}
		}
	} else {
		button.classList.remove('myButtonClicked');
		button.value = "on";
		gridItems.style.display = "block"; // Show the div
		for (var i = 0; i < camera.length; i++) {
			if (camera[i].Id === buttonId) {
				camera[i].Value = "on";
				updateImageSrc();
				break; // Once the update is done, exit the loop
			}
		}
	}
}
function resizeGrid(action) {
	if (action == 'plus') {
		size=size+50;
	} else if (action == 'minus' && size > 100) {
		size=size-50;
	}
	const gridContainer = document.getElementById('pictureGrid');
	const buttonSize = document.getElementById('size');
	buttonSize.innerHTML = "Size:" + size;
	gridContainer.style.gridTemplateColumns = `repeat(auto-fill, minmax(${size}px, 1fr))`;
}
function scaleimg(action) {
	if (action === 'scaledown') {
		scale = Math.max(scale - 10, 0); 
	} else if (action === 'scaleup') {
		scale = Math.min(scale + 10, 100); 
	}
	// Update the text of the middle button with the current value
	document.getElementById('scalenum').innerHTML = "Scale:" + scale + "%";
}
// Function to populate the buttons
// Loop through the array and create buttons for each camera
function createButton() {
//	document.addEventListener("DOMContentLoaded", function () {
		const buttonContainer = document.getElementById("buttonContainer");
		buttonContainer.innerHTML = '';
		for (var i = 0; i < camera.length; i++) {
			// Create a new button element
			var button = document.createElement("button");
			button.id = camera[i]["Id"];
			button.classList.add("myButton", "draggable");
			if(camera[i]["Value"] == "off") {
				button.classList.add("myButton", "draggable", "myButtonClicked");	
			}
			button.setAttribute("value", camera[i]["Value"]);
			// Set the button text using array values
			button.textContent = camera[i]['Name'];
			button.onclick = function() {
				toggleButtonState(this.id);};
				// setup the drag and drop stuff here
				button.setAttribute("draggable", true);
				button.addEventListener("dragstart", handleDragStart);
				button.addEventListener("dragover", handleDragOver);
				button.addEventListener("dragenter", handleDragEnter);
				button.addEventListener("dragleave", handleDragLeave);
				button.addEventListener("drop", handleDrop);
				button.addEventListener("dragend", handleDragEnd);
				buttonContainer.appendChild(button);
			}
		let dragSrcEl = null;
		function handleDragStart(e) {
			// Check if the button has been clicked
			if (this.value === "off") {
				e.preventDefault(); // Prevent drag if the button is clicked
				alert("Hidden buttons cannot be moved");
				return;
			}
			dragSrcEl = this;
			e.dataTransfer.effectAllowed = "move";
			e.dataTransfer.setData("text/html", this.innerHTML);
			e.dataTransfer.setData("text/plain", this.id);
		}
		function handleDragOver(e) {
			if (e.preventDefault) {
				e.preventDefault();
			}
			
			if (this.value === "off") {
				this.classList.remove("drop-target");
				this.classList.add("non-draggable");
			} else {
				this.classList.add("drop-target");
				this.classList.remove("non-draggable");
			}
			e.dataTransfer.dropEffect = "move";
			return false;
		}
		function handleDragEnter() {
			if (this.value === "off") {
				this.classList.add("over");
			}
		}
		function handleDragLeave() {
			this.classList.remove("over");
			this.classList.remove("drop-target");
			this.classList.remove("non-draggable");
		}
		function handleDrop(e) {
			if (e.stopPropagation) {
				e.stopPropagation();
			}
			// Check if the target button has been clicked
			if (this.value === "off") {
				return;
			}
			if (dragSrcEl !== this) {
			 // Get the parent container
        const buttonContainer = this.parentNode;

        // Insert the dragged element before the drop target
        buttonContainer.insertBefore(dragSrcEl, this);

        // Update the order in the grid and camera array
        reorderGrid();
			}
			return false;
		}
		function handleDragEnd() {
			const draggables = document.querySelectorAll(".draggable");
			draggables.forEach(function (draggable) {
				draggable.classList.remove("over");
				draggable.classList.remove("drop-target");
				draggable.classList.remove("non-draggable");
				reorderGrid();
			});
		}
//	});
}
// Function to create the grid
function createGrid() {
	// Clear existing grid items
	pictureGrid.innerHTML = '';
	pictureGrid.style.gridTemplateColumns = `repeat(auto-fill, minmax(${size}px, 1fr))`;
	// Loop to create grid items with images
	for (let i = 0; i < camera.length; i++) {
		// Create a div element for each grid item
		const gridItem = document.createElement('div');
		gridItem.className = 'grid-item';
		gridItem.id = 'grid_' + camera[i]["Id"];
		const img = document.createElement('img');
		if(camera[i]["Value"] == "off") {
			gridItem.style.display = "none"; // Hide the div
		}
		img.src = "";
		img.alt = camera[i].Name;
		img.id = "img_" + camera[i]["Id"];
		//Create navigation button right
		var button = document.createElement('button');
		button.classList.add('overlay-button');
		button.textContent = '→';
		button.addEventListener('click', function() {
			openNewWindow(camera[i]["Id"]);
		});
		// Append the button element to the grid item
		gridItem.appendChild(button);
		// Append the img element to the grid item
		gridItem.appendChild(img);
		// Append the grid item to the pictureGrid
		pictureGrid.appendChild(gridItem);
	}
	updateImageSrc();
}
function reorderGrid() {
	// Create a mapping of button IDs to camera indices
	var idToIndexMap = {};
	camera.forEach(function(cam, index) {
		idToIndexMap[cam.Id] = index;
	});
	// Get the buttonContainer and pictureGrid
	var buttonContainer = document.getElementById("buttonContainer");
	var pictureGrid = document.getElementById("pictureGrid");
	// Create a new array to store the reordered camera objects
	var reorderedCamera = [];
	// Iterate through the button IDs in the original order
	buttonContainer.childNodes.forEach(function(button) {
		if (button.nodeType === 1) { // Check if it's an element node
			var buttonId = button.id;
			var index = idToIndexMap[buttonId];
			// Add the corresponding camera object to the reordered array
			reorderedCamera.push(camera[index]);
			// Find the corresponding grid item
			var gridItem = document.getElementById("grid_" + buttonId);
			// Move the grid item to the end of the pictureGrid
			pictureGrid.appendChild(gridItem);
			// Update the image source
			var imgElement = document.getElementById("img_" + buttonId);
			imgElement.src = camera[index].Source;
		}
	});
	// Update the camera array with the reorderedCamera
	camera = reorderedCamera;
}
// Function to update image src. This is called every second (see above)
function updateImageSrc() {
	// Get all existing img elements in the pictureGrid
	const imgElements = pictureGrid.querySelectorAll('.grid-item img');
	for (let i = 0; i < camera.length; i++) {
		if(camera[i].Value == "on") {
			camera[i].Source = "https://" + location.host + "/zm/cgi-bin/nph-zms?mode=single&scale=" + scale + "&monitor=" + camera[i]["Id"] + "&token=" + token + "&" + Math.random();
			imgElements[i].src = camera[i].Source;
		} else {
			camera[i].Source = "";
			imgElements[i].src = camera[i].Source;
		}
	}
}
//function openNewWindow(id) {
//index = camera.findIndex(obj => obj["Id"] === id);
//	url = "https://" + location.host + "/zm/cgi-bin/nph-zms?mode=jpeg&scale=100&maxfps=1&buffer=1000&monitor=" + camera[index]["Id"] + "&token=" + token;
//	window.open(url, '_blank', 'width=600,height=400');
//}
// Function to open a new window linking to zoneminder mjpeg feed
function openNewWindow(id) {
index = camera.findIndex(obj => obj["Id"] === id);
	url = "https://" + location.host + "/zm/cgi-bin/nph-zms?mode=jpeg&scale=100&maxfps=1&buffer=1000&monitor=" + camera[index]["Id"] + "&token=" + token;
	window.open(url, '_blank', 'width=600,height=400');
}
// Functions to save and retrieve layouts to cookies
function saveToCookie() {
	// Create a copy of the 'camera' variable to avoid modifying the original array
	var cameraCopy = JSON.parse(JSON.stringify(camera));

	// Clear the 'Source' property for each camera in the copy
	cameraCopy.forEach(function(cameraItem) {
	cameraItem.Source = "";
	});
	// add scale and size to the cameraCopy cookie variable
	cameraCopy.push({"Size": size, "Scale": scale});
	// Convert the modified array to JSON and save it to a cookie
	var cameraJSON = JSON.stringify(cameraCopy);
	var expirationDate = new Date();
	expirationDate.setFullYear(expirationDate.getFullYear() + 1);
	document.cookie = "cameraData=" + cameraJSON + "; expires=" + expirationDate.toUTCString() + "; path=/";
	alert("Display saved");
}
function getFromCookie() {
	var name = "cameraData=";
	var decodedCookie = decodeURIComponent(document.cookie);
	var cookieArray = decodedCookie.split(';');
	for (var i = 0; i < cookieArray.length; i++) {
		var cookie = cookieArray[i];
		while (cookie.charAt(0) == ' ') {
			cookie = cookie.substring(1);
		}
		if (cookie.indexOf(name) == 0) {
			var cameraJSON = cookie.substring(name.length, cookie.length);
			camera = JSON.parse(cameraJSON);
			var sizescale = camera[camera.length - 1];
			size = sizescale["Size"];
			resizeGrid();
			scale = sizescale["Scale"];
			scaleimg();
			camera.pop(); // remove scale and size from camera variable
			createButton();
			createGrid();
			return JSON.parse(cameraJSON);
		}
	}
	return null;	
}
function deleteCookie() {
	var name = "cameraData=";
	document.cookie = name + "=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
	location.reload(); // Reload the page
}
</script>
</body>
</html>
