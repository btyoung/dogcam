/***************************************
 * DogCam Javascript
 ***************************************/

// jshint esnext: true
$(function () {
  // =========================================
  //  Motion Detection
  //
  // === Get canvas and set up  ===
  var mcanvas = document.getElementById('motion-marker');
  var mctx = mcanvas.getContext('2d');
  mctx.strokeStyle = "#FF0000";
  mctx.lineWidth = 3;

  // Set up socket to update the motion-marker canvas
  //  Restart it if it gets lost
  var build_motion_socket = function () {
    var socket = new WebSocket('ws://'+window.location.host+'/motion');

    socket.onmessage = function (msg) {
      mctx.clearRect(0, 0, mcanvas.width, mcanvas.height);
      $.each(JSON.parse(msg.data), function (idx, rect) {
        //console.log(rect[0], rect[1], rect[2], rect[3]);
        mctx.strokeRect(rect[0], rect[1], rect[2], rect[3]);
      });
    };

    socket.onclose = function (ev) {
      build_motion_socket();
    };
  };
  build_motion_socket();

  // ==========================================
  //  History View
  //
  var build_history_socket = function () {
    var socket = new WebSocket('ws://' + window.location.host + '/history');
    var history_records = [];  // (timestamp, ismotion) pairs

    socket.onmessage = function (msg) {
      data = JSON.parse(msg.data);
      // Add new data
      history_records.push(...data.records);
      // Clear data older than 12 hours
      //history_records = _.filter(history_records, entry => (data.now - entry[0]) > 12*3600);
      // Trigger redraw
      redraw_history_view(data.now, history_records);
    };

    socket.onclose = function (ev) {
      build_history_socket();
    };
  };
  build_history_socket();

  var img = document.getElementById('main-view');
  var slider = $('#time-select input');
  var time_markers = document.getElementById('time-markers');
  var tctx = time_markers.getContext('2d');
  var redraw_history_view = function(now, history_records) {
    // Clear
  //  tctx.setTransform(1.0, 0, 0, 1.0, 0, 0);
    tctx.clearRect(0, 0, time_markers.width, time_markers.height);
    // Draw records
/*    tctx.setTransform(*/
      //1.0 / (12.0*3600.0 / time_markers.width),  // Horizontal Scaling
      //0.0,                               // Horizontal Skewing
      //0.0,                               // Vertical Skewing
      //1.0,                               // Vertical Scaling
      //now - 12.0 * 3600.0,               // Left-most point
      //0.0                                // Lower point
    /*);*/
    _.each(history_records, function (record) {
      tctx.beginPath();
      if (record[1]) {
        tctx.strokeStyle = 'green';
      } else {
        tctx.strokeStyle = 'gray';
      }
      var x = (record[0] - (now - 12.0 * 3600.0)) * time_markers.width / (12.0 * 3600.0);
      tctx.moveTo(x, 10);
      tctx.lineTo(x, time_markers.height);
      tctx.stroke();

      slider.attr('max', now);
      slider.attr('min', now - 12*3600.0);
    });

    // Draw hour markers
    var nowdate = new Date(now * 1000.0);
    var rounded = new Date(nowdate.getTime());
    rounded.setMinutes(0); rounded.setSeconds(0); rounded.setMilliseconds(0);
    var offset = (nowdate.getTime() - rounded.getTime()) / 1000.0;
    //console.log(nowdate, rounded, offset);
    var hours = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];

    tctx.beginPath();
    tctx.strokeStyle = 'black';
    tctx.font = '12px Arial';
    tctx.moveTo(0, 0); tctx.lineTo(time_markers.width, 0); tctx.stroke();
    FTM = 15.0 * 60.0 * time_markers.width / (12.0 * 3600.0);  // Fifteen minutes
    _.each(hours, function (hr) {
      var xloc = time_markers.width - (offset + hr * 3600.0) *
          time_markers.width / (12.0 * 3600.0);

      tctx.moveTo(xloc, 0); tctx.lineTo(xloc, 20); tctx.stroke();
      tctx.moveTo(xloc+2*FTM, 0); tctx.lineTo(xloc+2*FTM, 10); tctx.stroke();
      tctx.moveTo(xloc+FTM, 0); tctx.lineTo(xloc+FTM, 5); tctx.stroke();
      tctx.moveTo(xloc+3*FTM, 0); tctx.lineTo(xloc+3*FTM, 5); tctx.stroke();
      tctx.fillText(rounded.getHours() - hr, xloc + 3, 20);
    });

    slider.on('change', function (ev) {
      //var idx = _.sortedIndex(history_records, this.value, 0);
      //var timestamp = history_records[idx][0];
      //console.log(timestamp);
      img.src = '/imgs/' + this.value + '.jpg';
      //mctx.fillText(new Date(this.value * 1000.0), mcanvas.height - 10, 10);
    });

    $('div.outer').on('click', function () { //addEventListener('click', function (ev) {
      console.log('resetting stream');
      img.src = '/vstream.mjpg';
    });
  };
});
