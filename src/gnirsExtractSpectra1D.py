#!/usr/bin/env python

# MIT License

# Copyright (c) 2015, 2017 Marie Lemoine-Busserolle

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

################################################################################
#                Import some useful Python utilities/modules                   #
################################################################################

import log, os, glob, ConfigParser
from astropy.io import fits
from pyraf import iraf

#---------------------------------------------------------------------------------------------------------------------#

def start(configfile):
    """
    This module contains all the functions needed to perform the full reduction of SCIENCE or TELLURIC data.

    Parameters are loaded from gnirs.cfg configuration file. This script will automatically detect if it is being run
    on telluric data or science data. There are 5 steps.

    INPUT FILES:
        - Configuration file
        - Science or Telluric frames
        - mdfshiftrefimage
        - masterflat
        - /database files from the appropriate calibrations directory

    OUTPUT FILES:
        - If telluric:  cleaned (optional), prepared, radiation-event corrected, reduced, spatial distortion corrected, 
          and transformed images
        - If science:  cleaned (optional), prepared, radiation-event corrected, reduced, spatial distortion corrected, 
          and transformed images

    Args:
        - kind (string): Either 'Science' or 'Telluric'
        - configfile: gnirs.cfg configuration file.
                - Paths to the Science (str), reduction truth value (boolean)
                  E.g. 'target/date/config/{Sci,Tel}_ObsID/{Calibrations,Intermediate}', True
                - Paths to the Tellurics (str), reduction truth value (boolean)
                  E.g. 'target/date/config/{Sci,Tel}_ObsID/{Calibrations,Intermediate}', True
                - manualMode (boolean): Enable optional manualModeging pauses? Default: False
                - overwrite (boolean): Overwrite old files? Default: False
                # And gnirsReduce specific settings
    """
    logger = log.getLogger('gnirsExtractSpectra1D.start')

    ###########################################################################
    ##                                                                       ##
    ##                  BEGIN - GENERAL EXTRACT 1D SETUP                     ##
    ##                                                                       ##
    ###########################################################################

    # Store current working directory for later use.
    path = os.getcwd()

    logger.info('####################################################')
    logger.info('#                                                  #')
    logger.info('#        Start Extracting GNIRS 1D Spectra         #')
    logger.info('#                                                  #')
    logger.info('####################################################\n')

    # Set up/prepare IRAF.
    iraf.gemini()
    iraf.gemtools()
    iraf.gnirs()

    # Reset to default parameters the used IRAF tasks.
    iraf.unlearn(iraf.gemini,iraf.gemtools,iraf.gnirs,iraf.imcopy)

    # From http://bishop.astro.pomona.edu/Penprase/webdocuments/iraf/beg/beg-image.html:
    # Before doing anything involving image display the environment variable stdimage must be set to the correct frame 
    # buffer size for the display servers (as described in the dev$graphcap file under the section "STDIMAGE devices") 
    # or to the correct image display device. The task GDEVICES is helpful for determining this information for the 
    # display servers.
    iraf.set(stdimage='imt1024')

    # Prepare the IRAF package for GNIRS.
    # NSHEADERS lists the header parameters used by the various tasks in the GNIRS package (excluding headers values 
    # which have values fixed by IRAF or FITS conventions).
    iraf.nsheaders("gnirs", logfile=logger.root.handlers[0].baseFilename)

    # Set clobber to 'yes' for the script. This still does not make the gemini tasks overwrite files, so: YOU WILL 
    # LIKELY HAVE TO REMOVE FILES IF YOU RE_RUN THE SCRIPT.
    us_clobber=iraf.envget("clobber")
    iraf.reset(clobber='yes')
    
    config = ConfigParser.RawConfigParser()
    config.optionxform = str  # make options case-sensitive
    config.read(configfile)
    
    # Read general config.
    manualMode = config.getboolean('defaults', 'manualMode')
    overwrite = config.getboolean('defaults', 'overwrite')
    
    # config required for extracting 1D spectra
    # Order of sections is important to later check for plausible peaks located for science targets by nsextract
    nsextractInter = config.getboolean('interactive', 'nsextractInter')
    calculateSpectrumSNR = config.getboolean('gnirsPipeline', 'calculateSpectrumSNR')
    
    combinedsrc = config.get('runtimeFilenames','combinedsrc')
    combinedsky = config.get('runtimeFilenames','combinedsky')
    extractRegularPrefix = config.get('runtimeFilenames','extractRegularPrefix')
    extractFullSlitPrefix = config.get('runtimeFilenames','extractFullSlitPrefix')
    extractStepwiseTracePrefix = config.get('runtimeFilenames','extractStepwiseTracePrefix')
    extractStepwisePrefix = config.get('runtimeFilenames','extractStepwisePrefix')
    databaseDir = config.get('runtimeFilenames','databaseDir')

    # extract1Spectra1D specific config
    useApall = config.getboolean('extractSpectra1D', 'useApall')
    subtractBkg = config.get('extractSpectra1D', 'subtractBkg')
    extractApertureRadius = config.getfloat('extractSpectra1D', 'extractApertureRadius')
    checkPeaksMatch = config.getboolean('extractSpectra1D', 'checkPeaksMatch')
    toleranceOffset = config.getfloat('extractSpectra1D', 'toleranceOffset')
    extractFullSlit = config.getboolean('extractSpectra1D','extractFullSlit')
    extractStepwise = config.getboolean('extractSpectra1D','extractStepwise')
    extractionStepSize = config.getfloat('extractSpectra1D','extractStepSize')
    extractApertureWindow = config.getfloat('extractSpectra1D','extractApertureWindow')

    ###########################################################################
    ##                                                                       ##
    ##                 COMPLETE - GENERAL EXTRACT 1D SETUP                   ##
    ##                                                                       ##
    ###########################################################################

    # gnirsExtractSpectra1D will first check if the reduction truth value of the science and telluric directories is 
    # True -- if it is, it will then check if the required spectra to be extracted are available in the directories
    # (and proceed only if it finds them there); else, it will warn the user and request to provide the spectra for 
    # extracting. If the reduction truth value of the science and telluric directories is False, the script will skip
    # extracting 1D spectra in those directories.

    # Loop through all the observation (telluric and science) directories to extract 1D spectra in each one.
    for section in ['TelluricDirectories', 'ScienceDirectories']:
        for obspath in config.options(section):

            if not config.getboolean(section, obspath):  # Only process directories marked True
                logger.debug('Skipping extraction of 1D spectra in %s', obspath)
                continue

            ###########################################################################
            ##                                                                       ##
            ##                  BEGIN - OBSERVATION SPECIFIC SETUP                   ##
            ##                                                                       ##
            ###########################################################################

            obspath += '/Intermediate'
            logger.info("Moving to observation directory: %s\n", obspath)
            os.chdir(obspath)
            iraf.chdir(obspath) 

            # Check if required combined spectra available in the observations directory
            logger.info("Checking if required combined spectra available.")

            if os.path.exists(obspath + '/' + combinedsrc):
                logger.info("Required combined source spectrum available.")
            else:
                logger.warning("Required combined source image not available.")
                logger.warning("please run gnirsCombineSpectra2D.py to create the combined source spectrum or provide")
                logger.warning("it manually in %s", obspath)
                logger.warning("Exiting script.\n")
                raise SystemExit
        
            if calculateSpectrumSNR:
                if os.path.exists(obspath + '/' + combinedsky):
                    logger.info("Required combined sky spectrum available.")
                else:
                    logger.warning("Parameter 'calculateSpectrumSNR' is 'True', but required combined sky spectrum")
                    logger.warning("not available. Setting the 'calculateSpectrumSNR' parameter for the current set")
                    logger.warning("of observations to 'False'.\n")
                    calculateSpectrumSNR = False

            logger.info("Required combined spectra check complete.")

            # Record the right number of orders (and file extensions) expected according to the GNIRS XD configuration.
            if 'LB_SXD' in obspath:
                orders = [3, 4, 5]
                # extractApertureRadius = 23 (+/-23 pixels or 6.9" covers almost the entire slit length, but
                # this is only appropriate for objects centred along length of slit (with absolute Q offset of 0).
                extractApertureWindow = 46   # [-46/2,46/2+6)   [-23.0 -17 -11 -5 1 7 13 19 23 29) warn the user if last step in extract >0.1" away from theend of the slit or if extractioj proceeding out of the slit
            elif 'LB_LXD' in obspath:
                orders = [3, 4, 5, 6, 7, 8]
                extractApertureWindow = 33    # [-33/2,33/2+6]  [-16.5 -10.5 -4.5 2.5 8.5 14.5 20.5]
            elif 'SB_SXD' in obspath:
                orders = [3, 4, 5, 6, 7, 8]
                extractApertureWindow = 46
            else:
                logger.error("#############################################################################")
                logger.error("#############################################################################")
                logger.error("#                                                                           #")
                logger.error("#     ERROR in telluric: unknown GNIRS XD configuration. Exiting script.    #")
                logger.error("#                                                                           #")
                logger.error("#############################################################################")
                logger.error("#############################################################################\n")
                raise SystemExit

            ###########################################################################
            ##                                                                       ##
            ##                 COMPLETE - OBSERVATION SPECIFIC SETUP                 ##
            ##            BEGIN EXTRACTING 1D SPECTRA FOR AN OBSERVATION             ##
            ##                                                                       ##
            ###########################################################################

            if manualMode:
                a = raw_input("About to enter extract 1D spectra.")

            if nsextractInter:
                subtractBkg = 'fit'
            
            if useApall:
                # This performs a weighted extraction
                apertureTracingColumns = 20
                extractSpectra1D(combinedsrc, extractRegularPrefix, nsextractInter, databaseDir, useApall, subtractBkg, \
                    apertureTracingColumns, extractApertureRadius, overwrite)
            else:
                apertureTracingColumns = 10
                extractSpectra1D(combinedsrc, extractRegularPrefix, nsextractInter, databaseDir, useApall, subtractBkg, \
                    apertureTracingColumns, extractApertureRadius, overwrite)

            # If the parameter 'calculateSpectrumSNR' is set to 'yes', the script will extract spectra from
            # the combined sky image; else, it will only extract spectra from the combined source image.
            if calculateSpectrumSNR:
                logger.info("Extracting the combined sky spectrum reduced without sky subtraction.\n")
                if useApall:
                    apertureTracingColumns = 20
                    extractSpectra1D(combinedsky, extractRegularPrefix, nsextractInter, databaseDir, useApall, subtractBkg, \
                        apertureTracingColumns, extractApertureRadius, overwrite)
                else:
                    apertureTracingColumns = 10
                    extractSpectra1D(combinedsky, extractRegularPrefix, nsextractInter, databaseDir, useApall, subtractBkg, \
                        apertureTracingColumns, extractApertureRadius, overwrite)

            if 'Science' in section:
                # Check if nsextractInter is set: if no, check if checkPeaksMatch is set: if yes, check if the
                # required telluric extraction reference files available in the telluric /database directory; else,
                # warn the user that both nsextractInter and checkPeaksMatch are not set, request the user to
                # manually check if the science target peak identified by task nsextract might
                # identify a wrong peak if the science target is not bright enough.

                # Get symbolic path to the tel database directory in the sci directory
                # Relative path/link expected to be at the top level of every sci directory
                scidatabasepath = obspath + '/' + databaseDir
                logger.info("Science database path: %s", scidatabasepath)
                telpath = '../Telluric/Intermediate'
                logger.info("Telluric path: %s", telpath)
                teldatabasepath = '../Telluric/Intermediate/' + databaseDir
                logger.info("Telluric database path: %s", teldatabasepath)
                sci_combinedsrc = obspath + '/' + combinedsrc
                tel_combinedsrc = telpath + '/' + combinedsrc

                if not nsextractInter:  # conditions if nsextract is not run interactively

                    if checkPeaksMatch:
                        logger.info("Checking if the required telluric extraction reference files available.")

                        # Check for the telluric /database directory in the current science observation directory
                        if os.path.exists(teldatabasepath):
                            logger.info("Telluric %s directory (possibly) containing telluric extraction ", databaseDir)
                            logger.info("reference files available.")
                            telCheck_flag = True
                        else:
                            logger.warning("Telluric %s directory (possibly) containing telluric extraction", databaseDir)
                            logger.warning("reference files not available.")
                            telCheck_flag = False

                        # Check for telluric extraction aperture reference files
                        telapfiles = glob.glob(teldatabasepath + '/ap' + nofits(os.path.basename(tel_combinedsrc)) + '_SCI_*')
                        tel_apfileslength = len(telapfiles)
                        if tel_apfileslength > 0:
                            logger.info("Reference files containing telluric extraction aperture details available in")
                            logger.info("the telluric %s directory.", databaseDir)
                            telCheck_flag = telCheck_flag and True
                        else:
                            logger.warning("Reference files containing telluric extraction aperture details not")
                            logger.warning("available in the telluric %s directory.", databaseDir)
                            telCheck_flag = telCheck_flag and False
                            
                        logger.info("Required telluric extraction reference files check complete.\n")

                        if telCheck_flag:
                            logger.info("All telluric extraction reference files available in %s\n", teldatabasepath)
                            sci_apfileslength = len(glob.glob(scidatabasepath + '/ap' + nofits(os.path.basename(sci_combinedsrc)) + '_SCI_*'))
                            
                            logger.info("Finding palusible peaks used by nsextract.")
                            telpeaks = peaksFind(teldatabasepath, tel_apfileslength, nofits(combinedsrc))
                            scipeaks = peaksFind(scidatabasepath, sci_apfileslength, nofits(combinedsrc))
                            logger.info("Completed finding palusible peaks used by nsextract.")

                            logger.info("Matching the peaks found by nsextract.")
                            scitelPeaksMatched, sciReExtract = peaksMatch(obspath, telpath, combinedsrc, scipeaks, telpeaks, \
                                toleranceOffset)
                            logger.info("Completed matching the peaks found by nsextract.")

                            # Re-extract combined science 2D source spectrum if needed
                            if sciReExtract:
                                logger.info("Re-extracting one or more science spectra.")
                                newtelapfilePrefix = 're'
                                useApall = 'yes'
                                apertureTracingColumns = 20
                                reExtractSpectra1D(scidatabasepath, teldatabasepath, telpath, scitelPeaksMatched, \
                                    sci_combinedsrc, tel_combinedsrc, newtelapfilePrefix, orders, nsextractInter, extractRegularPrefix, \
                                    databaseDir, useApall, subtractBkg, apertureTracingColumns, extractApertureRadius)
                                logger.info("Completed re-extracting one or more science spectra.")
                            else:
                                logger.info("Not re-extracting any science spectra.")
                                pass
                        else:
                            logger.warning("Parameter 'checkPeakMatch' is set to 'True', but one or more telluric")
                            logger.warning("extraction reference files not available in")
                            logger.warning("%s", teldatabasepath)
                            logger.warning("Setting 'checkPeaksMatch' to 'False'.\n")
                            checkPeaksMatch = False

                            # TODO(Viraja):  Can ask the user if they want to perform checkPeaksMatch and set it at
                            # this point. This would probably need the checks to be called as a function because the
                            # script must check for the required telluric extraction reference files once the
                            # parameter 'checkPeaksMatch' is set to 'True'.

                    else:
                        logger.warning("Parameters 'nsextractInter' and 'checkPeaksMatch' both set to 'False'.")
                        logger.warning("Please check manually if nsextract identified the science peaks at expected")
                        logger.warning("locations.\n")


            # TODO(Viraja):  Set these up once the respective functions are ready.
            if extractFullSlit:
                pass
            else:
                pass


            if extractStepwise:
                # Extract in steps on either side of the peak
                useApall = 'yes'
                pass
            else:
                pass

        logger.info("##############################################################################")
        logger.info("#                                                                            #")
        logger.info("#  COMPLETE - Extracting 1D spectra completed for                            #")
        logger.info("#  %s", obspath)
        logger.info("#                                                                            #")
        logger.info("##############################################################################\n")

    # Return to directory script was begun from.
    os.chdir(path) 
    iraf.chdir(path)

    return

##################################################################################################################
#                                                     ROUTINES                                                   #
##################################################################################################################

def nofits(filename):
    """
    Remove extension '.fits' from the filename.
    """
    logger = log.getLogger('gnirsExtractSpectra1D.nofits')
    
    return filename.replace('.fits', '')

#---------------------------------------------------------------------------------------------------------------------#

def extractSpectra1D(inimage, outPrefix, interactive, databaseDir, useApall, subtractBkg, apertureTracingColumns, \
    extractApertureRadius, overwrite):
    """
    Extracting 1D spectra from the combined 2D spectra using nsextract.
    """
    logger = log.getLogger('gnirsSxtractSpectra1D.extractSpectra1D')
    logger.debug('%s', os.getcwd())
    logger.debug('%s', inimage)

    if os.path.exists(outPrefix + inimage):
        if overwrite:
            logger.warning("Removing old %s", outPrefix + inimage)
            os.remove(outPrefix + inimage)
        else:
            logger.warning("Old %s exists and -overwrite not set - skipping nsextract for observations.", outPrefix + inimage)
            return

    iraf.nsextract(inimages=inimage, outspectra='', outprefix=outPrefix, dispaxis=1, database='', line=700, 
        nsum=apertureTracingColumns, ylevel='INDEF', upper=extractApertureRadius, lower=-extractApertureRadius, 
        background=subtractBkg, fl_vardq='yes', fl_addvar='no', fl_skylines='yes', fl_inter=interactive, fl_apall=useApall, 
        fl_trace='no', aptable='gnirs$data/apertures.fits', fl_usetabap='no', fl_flipped='yes', fl_project='yes', 
        fl_findneg='no', bgsample='*', trace='', tr_nsum=10, tr_step=10, tr_nlost=3, tr_function='legendre', tr_order=5, 
        tr_sample='*', tr_naver=1, tr_niter=0, tr_lowrej=3.0, tr_highrej=3.0, tr_grow=0.0, weights='variance', 
        logfile=logger.root.handlers[0].baseFilename, verbose='yes', mode='al')

# ----------------------------------------------------------------------------------------------------------------------

def peaksFind(databasepath, apfileslength, combinedimage):
    """
    Check the telluric or science extraction reference files in the telluric directory databases to find the location 
    of the respective peaks.
    """
    logger = log.getLogger('gnirsReduce.peaksFind')

    peaks = []
    for i in range(apfileslength):
        print(i)
        apfile = open(databasepath+'/ap'+combinedimage+'_SCI_'+str(i+1)+'_', 'r') 
        for line in apfile:
            # Get the peak location, which is the number in the second column of the line beginning with 'center'
            if 'center' in line:
                peaks.append(line.split()[1])
            else:
                logger.error('Peak not found')
                peaks.append('Peak not found')  # None?
    return peaks

# ----------------------------------------------------------------------------------------------------------------------

def peaksMatch(obspath, telpath, combinedimage, scipeaks, telpeaks, toleranceOffset):
    """
    Checks is NSEXTRACT located the peak of the science at a resonable location along the slit given the aperture
    center of extraction of the telluric.

    For faint targets, NSEXTRACT often finds a noise peak instead of the science peak. In such cases, it is advisable  
    to check the aperture center of extraction of the science with respect to the telluricre and re-extract at the 
    expected location. Here,
        First, check that all the extensions of the combined 2D image have been extracted.
        Third, look the science and telluric absolute Q offsets and determine if the relative location of the target 
        peak was correct.
    If not, re-extract at the expected location.
    """
    logger = log.getLogger('gnirsReduce.peaksMatch')

    # TODO: Get the P,Q from the obslog.  This means we need scipath and telpath.

    # Find absolute Q offsets of the combined science and telluric images from their respective last acquisition images
    sciacqHeader = fits.open(sciacq)[0].header
    scisrccombHeader = fits.open(scisrccomb)[0].header
    scisrccombQoffset = abs(sciacqHeader['QOFFSET'] - scisrccombHeader['QOFFSET'])

    telacqHeader = fits.open(telacq)[0].header
    telsrccombHeader = fits.open(telsrccomb)[0].header
    telsrccombQoffset = abs(telacqHeader['QOFFSET'] - telsrccombHeader['QOFFSET'])

    pixelscale = scisrccombHeader['PIXSCALE']
    pixeldifference = (scisrccombQoffset - telsrccombQoffset)/pixelscale  # units: [pixels]

    peaksMatched = []
    # nsextract should find the spectrum within a 'tolerance' pixels of expected location. This depends on how well the 
    # observer centred the target along the slit. Here, we use 5 pixels as a reasonable tolerance level. A more robust
    # way would be to use some measure of whether the peak found by nsextract was real, e.g. counts + FWHM. However, 
    # this information is not recorded in database.
    for i in range(len(scipeaks)):
        expectedPeak = float(telpeaks[i]) + pixeldifference
        if scipeaks[i] == 'Peak not found':
            logger.warning("In extension %d for the science, nsextract did not extract anything. Re-extracting ", i)
            logger.warning("the spectrum forcing the aperture to be at the expected peak location %.4g", expectedPeak)
            peaksMatched.append(False)
            reExtract = True
        else:    
            locatedPeak = float(scipeaks[i])
            if abs(locatedPeak - expectedPeak) < toleranceOffset:
                logger.info("In extension %d for the science, nsextract detected the spectrum close to the ", i)
                logger.info("expected peak location along slit (located position = %s vs. expected ", locatedPeak)
                logger.info("position = %s .", expectedPeak)
                peaksMatched.append(True)
                reExtract = False
            else:
                logger.warning("In extension %d for the science, nsextract extracted an unexpected peak location ", i)
                logger.warning("along the slit (located position = %s vs. expected position = ", locatedPeak)
                logger.warning("%s . It is probably extracting noise; re-extracting the spectrum ", expectedPeak)
                logger.warning("forcing the aperture to be at the expected peak location.'")
                peaksMatched.append(False)
                reExtract = True

    return peaksMatched, reExtract

# ----------------------------------------------------------------------------------------------------------------------

def reExtractSpectra1D(scidatabasepath, teldatabasepath, telpath, scitelPeaksMatched, sci_combinedsrc, \
    tel_combinedsrc, newtelapfilePrefix, orders, nsextractInter, extractRegularPrefix, databaseDir, useApall, subtractBkg, \
    apertureTracingColumns, extractApertureRadius):
    """
    """
    logger = log.getLogger('gnirsReduce.reExtractSpectra1D')

    logger.info("Creating new aperture files in database.")
    for i in range(len(orders)):
        extension = i+1

        # There is some trouble replacing only the database files for the extracted spectra that were not well centred.
        # So, simply replacing all science database files but using the ones for which nsextract located the peaks at 
        # the right positions.
        oldsciapfile = scidatabasepath+'/ap'+sci_combinedsrc[:-5]+'_SCI_'+str(extension)+'_'
        if os.path.exists(oldsciapfile):
            os.remove(oldsciapfile)
        oldtelapfile = open(teldatabasepath+'ap'+tel_combinedsrc+'_SCI_'+str(extension)+'_', 'r')
        newtelapfile = open(teldatabasepath+'ap'+newtelapfilePrefix+tel_combinedsrc+'_SCI_'+str(extension)+'_', 'w')
        if not peaks_flag[i]:
            # TODO(Viraja):  Check if there is a better way to replace the peak values then how it is done below.
            replacetelapfile  = oldtelapfile.read().replace(telpeaks[i], str(float(telpeaks[i])+pixeldifference)+' ').replace(tel_combinedsrc, newtelapfilePrefix+tel_combinedsrc)
        else:
            replacetelapfile  = oldtelapfile.read().replace(telpeaks[i], telpeaks[i]+' ').replace(tel_combinedsrc, newtelapfilePrefix+tel_combinedsrc)
        newtelapfile.write(replacetelapfile)
        oldtelapfile.close()
        newtelapfile.close()
        
    shutil.copy(telpath+'/'+tel_combinedsrc, telpath+'/'+newtelapfilePrefix+tel_combinedsrc)
    os.remove('v'+sci_combinedsrc)
    
    # These settings in nsextract will force it to use the aperture size and center in the revised telluric apfiles
    iraf.nsextract(inimages=sci_combinedsrc, outspectra='', outprefix=extractRegularPrefix, dispaxis=1, database='', line=700, \
        nsum=apertureTracingColumns, ylevel='INDEF', upper=str(extractApertureRadius), \
        lower=-str(extractApertureRadius), background=subtractBkg, fl_vardq='yes', fl_addvar='no', fl_skylines='yes', \
        fl_inter=nsextractInter, fl_apall=useApall, fl_trace='no', aptable='gnirs$data/apertures.fits', \
        fl_usetabap='no', fl_flipped='yes', fl_project='yes', fl_findneg='no', bgsample='*', \
        trace=telpath+'/'+newtelapfilePrefix+tel_combinedsrc, tr_nsum=10, tr_step=10, tr_nlost=3, \
        tr_function='legendre', tr_order=5, tr_sample='*', tr_naver=1 ,tr_niter=0, tr_lowrej=3.0, tr_highrej=3.0, \
        tr_grow=0.0, weights='variance', logfile=logger.root.handlers[0].baseFilename, verbose='yes', mode='al')

    # NOTE:  There is a slight complication here - we occasionally find that nsextract locates the aperture too close 
    # to the end of the slit. Due to this, it exits with an "Aperture too large" error and spectra are not extracted 
    # for one or more orders. XDGNIRS works around that in XDpiped.csh, where it ignores this error. However, the 
    # error can occur for other reasons. So, here we check if all file extensions are present for the extracted target
    # file (should really add other files as well...)  Viraja:  I believe the other files are the database files.
    extractedSpectraExtensions = iraf.gemextn(inimages=sci_combinedsrc, check='exists,mef', process='expand', \
        index='', extname='SCI', extversion='', ikparams='', omit='', replace='', outfile='STDOUT', \
        logfile=logger.root.handlers[0].baseFilename, glogpars='', verbose='yes', fail_count='0', count='20', \
        status='0', Stdout=1)
    if len(extractedSpectraExtensions) != len(orders):
        # TODO(Viraja):  Can ask the user to change the extractApertureRadius and redo the extraction. Check with 
        # Andy if this could work. If yes, I think this is something that can also be done when the spectra are first 
        # extracted non-interactively (although I am not sure if that would make sense if we do a peak check).
        logger.error("The combined science image file contains only %d extensions.", len(extractedSpectraExtensions))
        logger.error("Please run gnirsCombineSpectra2D.py to create the combined 2D science image with the right")
        logger.error("number of extensions or provide the combined science image with the right number of extensions")
        logger.error("manually. Exiting script.")
        raise SystemExit

#---------------------------------------------------------------------------------------------------------------------#
'''
def stepwiseExtractSpectra1D(combinedimage, nsextractInter, useApall, apertureTracingColumns):
    """
    Extracts science spectra along (approximately) the full slit. 
    
    This method is appropriate for objects centred along length of slit (absolute Q offset for the science = 0). The 
    effect, if nsextract does not find a spectrum centred along the slit, is not known at this point.
    
    CAUTION NOTE:  From XDGNIRS, full slit and stepwise extractions have not been used or tested thoroughly. So, 
    please double check your results.
    """
    logger = log.getLogger('gnirsReduce.stepwiseExtractSpectra1D')

    iraf.nsextract(inimages=combinedimage, outspectra='', outprefix='a', dispaxis=1, database='', line=700, \
        nsum=apertureTracingColumns, ylevel='INDEF', upper=str(extractApertureRadius), \
        lower='-'+str(extractApertureRadius), background='none', fl_vardq='yes', fl_addvar='no', fl_skylines='yes',\
        fl_inter=nsextractInter, fl_apall=useApall, fl_trace='no', aptable='gnirs$data/apertures.fits', \
        fl_usetabap='no', fl_flipped='yes', fl_project='yes', fl_findneg='no', bgsample='*', trace='', tr_nsum=10, \
        tr_step=10, tr_nlost=3, tr_function='legendre', tr_order=5, tr_sample='*', tr_naver=1, tr_niter=0, \
        tr_lowrej=3.0, tr_highrej=3.0, tr_grow=0.0, weights='variance', logfile=logger.root.handlers[0].baseFilename, \
        verbose='yes', mode='al')

    # First trace the peak to make sure that the same part of the object is extracted in each step along the slit for  
    # all orders. This is required when the structure is complex, e.g., structure varying in the spectral direction in  
    # an extended object such as a galaxy; otherwise the spectra can have offsets between orders.
    
    # This first nsextract step performed outside the loop gets the trace into the science extraction database to be 
    # used during the actual stepwise extraction.
    extractApertureRadius = 3
    iraf.nsextract(inimages=combinedimage, outspectra='extractionStepwiseTraceReference', outprefix='x', dispaxis=1, \
        database='', line=700, nsum=apertureTracingColumns, ylevel='INDEF', upper=str(extractApertureRadius), \
        lower='-'+str(extractApertureRadius), background='none', fl_vardq='yes', fl_addvar='no', fl_skylines='yes',\
        fl_inter=nsextractInter, fl_apall=useApall, fl_trace='yes', aptable='gnirs$data/apertures.fits', \
        fl_usetabap='no', fl_flipped='yes', fl_project='no', fl_findneg='no', bgsample='*', trace='', tr_nsum=10, \
        tr_step=10, tr_nlost=3, tr_function='legendre', tr_order=5, tr_sample='300:1000', tr_naver=1, tr_niter=0, \
        tr_lowrej=3.0, tr_highrej=3.0, tr_grow=0.0, weights='variance', logfile=logger.root.handlers[0].baseFilename, \
        verbose='yes', mode='al')
    
    # This second step is never done interactively, because it uses extraction details from the previous call to 
    # nsextract
    nsextractInter = False
    for i in range(-extractionStepradius,extractionStepradius,extractionStepSize):
        iraf.nsextract(inimages=combinedimage, outspectra='', outprefix='s'+str(n), dispaxis=1, database='', line=700,\
            nsum=apertureTracingColumns, ylevel='INDEF', upper=i+extractionStepSize, lower=i, background='none', \
            fl_vardq='yes', fl_addvar='no', fl_skylines='yes', fl_inter=nsextractInter, fl_apall=useApall, \
            fl_trace='no', aptable='gnirs$data/apertures.fits', fl_usetabap='no', fl_flipped='yes', fl_project='yes', \
            fl_findneg='no', bgsample='*', trace='extractionStepwiseTraceReference', tr_nsum=10, tr_step=10, \
            tr_nlost=3, tr_function='legendre', tr_order=5, tr_sample='*', tr_naver=1, tr_niter=0, tr_lowrej=3.0, \
            tr_highrej=3.0, tr_grow=0.0, weights='variance', logfile=logger.root.handlers[0].baseFilename, \
            verbose='yes', mode='al')
'''
#---------------------------------------------------------------------------------------------------------------------#

if __name__ == '__main__':
    log.configure('gnirs.log', filelevel='INFO', screenlevel='DEBUG')
    start('gnirs.cfg')
