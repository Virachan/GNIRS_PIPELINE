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

import log, os, sys, pkg_resources, glob, shutil, ConfigParser, cleanir
from astropy.io import fits
from pyraf import iraf

## IMPORTANT NOTE:  The command line options are not available for GNIRS as of August 2019.

#---------------------------------------------------------------------------------------------------------------------#

def start(configfile):
    """
    This module contains all the functions needed to reduce GNIRS GENERAL BASELINE CALIBRATIONS.

    INPUT FILES FOR BASELINE CALIBRATION:

    INPUT FILES:
        - Configuration file                                                                                                                                                                                                                                              
        - All calibration frames
        - QH flat frames
        - IR flat frames
        - Arc frames
        - Pinhole flat frames

    OUTPUT FILES:
        - masterflat.fits
        - wavelength calibrated arc image

    Args:
        - configfile: gnirs.cfg configuration file
                - Paths to the calibrations (str), reduction truth value (boolean): 
                  E.g. 'target/date/config/{Sci,Tel}_ObsID/{Calibrations,Intermediate}', True
                - manualMode (boolean): Enable optional manualModeging pauses? Default: False
                - overwrite (boolean): Overwrite old files? Default: False
                - start (int): starting step of calibration reductions. Specified at command line with -a. Default: 1
                - stop (int): stopping step of calibration reductions. Specified at command line with -z. Default: 5
                - cleanir_QHflats (boolean): Cleaning QH flat frames. Default: False
                - cleanir_IRflats (boolean): Cleaning IR flat frames. Default: False
                - cleanir_arcs (boolean): Cleaning arc frames. Default: False
                - cleanir_pinholes (boolean): Cleaning pinhole flat frames. Default: False
                - nsprepareInter (boolean): Running nsprepare interactively? Default: False
                - nscombineInter (boolean): Running nscombine interactively? Default: False
                - nssdistInter (boolean): Running nssdist interactively? Default: False
                - nswavelengthInter (boolean): Running nswavelength interactively? Default: False
                - nsfitcoordsInter (boolean): Running nsfitcoords interactively? Default: False
    """
    logger = log.getLogger('gnirsBaselineCalibration.start')

    # Store current working directory for later use.
    path = os.getcwd()

    logger.info('##################################################')
    logger.info('#                                                #')
    logger.info('# Start the GNIRS Baseline Calibration Reduction #')
    logger.info('#                                                #')
    logger.info('##################################################\n')
    
    # Set up/prepare IRAF.
    iraf.gemini()
    iraf.gnirs()
    iraf.gemtools()

    # Reset to default parameters the used IRAF tasks.
    iraf.unlearn(iraf.gemini,iraf.gemtools,iraf.gnirs)

    # From http://bishop.astro.pomona.edu/Penprase/webdocuments/iraf/beg/beg-image.html:
    # Before doing anything involving image display the environment variable stdimage must be set to the correct frame 
    # buffer size for the display servers (as described in the dev$graphcap file under the section "STDIMAGE devices") 
    # or to the correct image display device. The task GDEVICES is helpful for determining this information for the 
    # display servers.
    iraf.set(stdimage='imt1024')

    # Prepare the IRAF package for GNIRS.
    # NSHEADERS lists the header parameters used by the various tasks in the GNIRS package (excluding headers values 
    # which have values fixed by IRAF or FITS conventions).
    iraf.nsheaders("gnirs",logfile=logger.root.handlers[0].baseFilename)

    # Set clobber to 'yes' for the script. This still does not make the gemini tasks overwrite files, so: YOU WILL 
    # LIKELY HAVE TO REMOVE FILES IF YOU RE_RUN THE SCRIPT.
    user_clobber=iraf.envget("clobber")
    iraf.reset(clobber='yes')

    logger.info("Parameters read from %s", configfile)

    config = ConfigParser.RawConfigParser()
    config.optionxform = str  # make options case-sensitive
    config.read(configfile)
    
    # Read general config
    manualMode = config.getboolean('defaults','manualMode')
    overwrite = config.getboolean('defaults','overwrite')
    
    # Read config required for flux calibration
    nsprepareInter = config.getboolean('interactive','nsprepareInter')
    nsflatInter = config.getboolean('interactive','nsflatInter')
    nscombineInter = config.getboolean('interactive','nscombineInter')
    nssdistInter = config.getboolean('interactive','nssdistInter')
    nswavelengthInter = config.getboolean('interactive','nswavelengthInter')
    nsfitcoordsInter = config.getboolean('interactive','nsfitcoordsInter')

    cleanirPrefix = config.get('runtimeFilenames','cleanirPrefix')
    preparedPrefix = config.get('runtimeFilenames','preparedPrefix')
    reducedPrefix = config.get('runtimeFilenames','reducedPrefix')
    QHflat = config.get('runtimeFilenames','QHflat')
    QHflat_bpm = config.get('runtimeFilenames','QHflat_bpm')
    IRflat = config.get('runtimeFilenames','IRflat')
    IRflat_bpm = config.get('runtimeFilenames','IRflat_bpm')
    masterflat = config.get('runtimeFilenames','masterflat')
    combinedarc = config.get('runtimeFilenames','combinedarc')
    databaseDir = config.get('runtimeFilenames','databaseDir')
    waveCalibPrefix = config.get('runtimeFilenames','waveCalibPrefix')
    fitcoordsPrefix = config.get('runtimeFilenames','fitcoordsPrefix')
    transformPrefix = config.get('runtimeFilenames','transformPrefix')

    # Read calibrationReduction specfic config
    start = config.getint('calibrationReduction','Start')
    stop = config.getint('calibrationReduction','Stop')
    cleanir_QHflats = config.getboolean('calibrationReduction','cleanir_QHflats')
    cleanir_IRflats = config.getboolean('calibrationReduction','cleanir_IRflats')
    cleanir_arcs = config.getboolean('calibrationReduction','cleanir_arcs')
    cleanir_pinholes = config.getboolean('calibrationReduction','cleanir_pinholes')

    ################################################################################
    # Define Variables, Reduction Lists AND identify/run number of reduction steps #
    ################################################################################

    # Loop over the Calibrations directories and reduce the calibrations for the ones with caibration_direcotries True.
    for calpath in config.options('CalibrationDirectories'):
        if config.getboolean('CalibrationDirectories',calpath):

            iraf.chdir(calpath)

            # Print the current directory of calibrations being processed.
            logger.info("Currently working on calibrations in %s\n", calpath)
            
            # Record the right number of order expected according to the GNIRS XD configuration.
            if 'LB_SXD' in calpath:
                orders = [3, 4, 5]
            elif 'LB_LXD' in calpath:
                orders = [3, 4, 5, 6, 7, 8]
            elif 'SB_SXD' in calpath:
                orders = [3, 4, 5, 6, 7, 8]
                nominal_wavelengths = ([0, 0], [18690,25310], [14020, 18980], [11220, 15180], [9350, 12650],
                    [8020, 10840], [7020, 9480])
                advertised_accuracy_percent = 5
            else:
                logger.error("#############################################################################")
                logger.error("#############################################################################")
                logger.error("#                                                                           #")
                logger.error("#    ERROR in calibrate: unknown GNIRS XD configuration. Exiting script.    #")
                logger.error("#                                                                           #")
                logger.error("#############################################################################")
                logger.error("#############################################################################\n")
                raise SystemExit

            # Check if lists of each type of calibration available in the Calibrations directory.
            logger.info("Checking if all required lists available in %s", calpath)
            
            allcalsfilename = 'all.list'
            if os.path.exists(allcalsfilename):
                logger.info("List of all calibrations available.")
                allcalslist = open(allcalsfilename, "r").readlines()
                allcalslist = [filename.strip() for filename in allcalslist]
                rawHeader = fits.open(allcalslist[0])[0].header
            else:
                logger.warning("List of all calibrations available.")
                logger.warning("Please run make_lists.py to generate the required list or provide it manually in")
                logger.warning("%s", calpath)
                logger.warning("Exiting script.\n")
                raise SystemExit
            
            QHflatsfilename = 'QHflats.list'
            if os.path.exists(QHflatsfilename):
                logger.info("List of QHflats available.")
                QHflatslist = open(QHflatsfilename, "r").readlines()
                QHflatslist = [filename.strip() for filename in QHflatslist]
            else:
                logger.warning("List of QHflats available.")
                logger.warning("Please run make_lists.py to generate the required list or provide it manually in")
                logger.warning("%s", calpath)
                logger.warning("Exiting script.\n")
                raise SystemExit

            IRflatsfilename = 'IRflats.list'
            if os.path.exists(IRflatsfilename):
                logger.info("List of IRflats available.")
                IRflatslist = open(IRflatsfilename, "r").readlines()
                IRflatslist = [filename.strip() for filename in IRflatslist]
            else:
                logger.warning("List of IRflats available.")
                logger.warning("Please run make_lists.py to generate the required list or provide it manually in")
                logger.warning("%s", calpath)
                logger.warning("Exiting script.\n")
                raise SystemExit
            
            pinholesfilename = 'pinholes.list'
            if os.path.exists(pinholesfilename):
                logger.info("List of pinholes available.")
                pinholeslist = open(pinholesfilename, "r").readlines()
                pinholeslist = [filename.strip() for filename in pinholeslist]
                # Write the name of the first flat in pinholeslist for which spatial distortion will be calculated.
                sdistrefimage = reducedPrefix + preparedPrefix + pinholeslist[0]
            else:
                logger.warning("List of pinholes available.")
                logger.warning("Please run make_lists.py to generate the required list or provide it manually in")
                logger.warning("%s", calpath)
                logger.warning("Exiting script.\n")
                raise SystemExit
            
            arcsfilename = 'arcs.list'
            if os.path.exists(arcsfilename):
                logger.info("List of arcs available.")
                arcslist = open(arcsfilename, "r").readlines()
                arcslist = [filename.strip() for filename in arcslist]
            else:
                logger.warning("List of arcs available.")
                logger.warning("Please run make_lists.py to generate the required list or provide it manually in")
                logger.warning("%s", calpath)
                logger.warning("Exiting script.\n")
                raise SystemExit

            logger.info("Required lists check complete.\n")
        
            # Check start and stop values for reduction steps. Ask user for a correction if input is not valid.
            valindex = start
            while valindex > stop  or valindex < 1 or stop > 5:
                logger.warning("######################################################################")
                logger.warning("######################################################################")
                logger.warning("#                                                                    #")
                logger.warning("#   WARNING in calibrate: invalid start/stop values of calibration   #")
                logger.warning("#                         reduction steps.                           #")
                logger.warning("#                                                                    #")
                logger.warning("######################################################################")
                logger.warning("######################################################################\n")

                valindex = int(raw_input("Please enter a valid start value (1 to 5, default 1): "))
                stop = int(raw_input("Please enter a valid stop value (1 to 5, default 5): "))

            while valindex <= stop:
            
                #############################################################################
                ##  STEP 1: Clean calibration frames.                                      ##
                ##  Output: Cleaned QHflats, IRflats, arcs, and pinholes.                  ##
                #############################################################################

                if valindex == 1:
                    ## this step is not modified to work with the GNIRS pipeline as of July 2019
                    if manualMode:
                        a = raw_input("About to enter step 1: clean calibration frames.")

                    if cleanir_QHflats:
#                        cleanNoise(QHflatslist, cleanirPrefix, overwrite)
                        pass
                    else:
                        logger.warning("######################################################################")
                        logger.warning("######################################################################")
                        logger.warning("#                                                                    #")
                        logger.warning("#              WARNING in calibrate: QHflats not cleaned.            #")
                        logger.warning("#                                                                    #")
                        logger.warning("######################################################################")
                        logger.warning("######################################################################")
                
                    if cleanir_IRflats:
#                        cleanNoise(IRflatslist, cleanirPrefix, overwrite)
                        pass
                    else:
                        logger.warning("######################################################################")
                        logger.warning("######################################################################")
                        logger.warning("#                                                                    #")
                        logger.warning("#               WARNING in calibrate: IRflats not cleaned.           #")
                        logger.warning("#                                                                    #")
                        logger.warning("######################################################################")
                        logger.warning("######################################################################")

                    if cleanir_arcs:
#                        cleanNoise(arcslist, cleanirPrefix, overwrite)
                        pass
                    else:
                        logger.warning("######################################################################")
                        logger.warning("######################################################################")
                        logger.warning("#                                                                    #")
                        logger.warning("#               WARNING in calibrate: arcs not cleaned.              #")
                        logger.warning("#                                                                    #")
                        logger.warning("######################################################################")
                        logger.warning("######################################################################")

                    if cleanir_pinholes:
#                        cleanNoise(pinholeslist, cleanirPrefix, overwrite)
                        pass
                    else:
                        logger.warning("######################################################################")
                        logger.warning("######################################################################")
                        logger.warning("#                                                                    #")
                        logger.warning("#              WARNING in calibrate: pinholes not cleaned.           #")
                        logger.warning("#                                                                    #")
                        logger.warning("######################################################################")
                        logger.warning("######################################################################")
                    
                    # NOTE:  At this point in XDGNIRS, StatsAndPrepartXD.py checks for any deviations in statistical
                    # parameters between the raw and the cleaned images. Since cleaning is not incorporated yet in 
                    # this pipeline, this check is skipped here.

                    # NOTE:  StatsAndPrepartXD.py also records any deviations in the mean values of cleaned QHfkats 
                    # and IRflats before preparing calibrations for reduction (here, step 2 prepareCalibrations). If 
                    # cleaning is skipped, statistics is done on the raw flat frames. This check is skipped in this 
                    # pipeline for now, but it could be useful to do.

                    logger.info("##################################################################")
                    logger.info("#                                                                #")
                    logger.info("#          STEP 1: Clean calibration frames - COMPLETED          #")
                    logger.info("#                                                                #")
                    logger.info("##################################################################\n")
                    
                #############################################################################
                ##  STEP 2: Preparing all calibration frames for further processing.       ##
                ##  Output: All prepared and reduced calibration images.                   ##
                #############################################################################

                elif valindex == 2:
                    if manualMode:
                        a = raw_input("About to enter step 2: preparing all calibration frames.")
                    
                    # Use the most appropriate bad pixel mask. For data taken Before the summer 2012 lens replacement,
                    # use 'gnirs$data/gnirsn_2011apr07_bpm.fits'; after summer 2012, use 
                    # 'gnirs$data/gnirsn_2012dec05_bpm.fits'. Use keyword 'ARRAYID' in the raw file header to check
                    # which camera was used for observations, and accordingly set parameter 'bpm' for the bpmfile to be
                    # used from the gnirs$database.
                    arrayid = rawHeader['ARRAYID'].strip()
                    if arrayid == 'SN7638228.1':
                        bpmfile = 'gnirs$data/gnirsn_2011apr07_bpm.fits'
                    elif arrayid == 'SN7638228.1.2':
                        bpmfile = 'gnirs$data/gnirsn_2012dec05_bpm.fits'
                    else:
                        logger.error("######################################################################")
                        logger.error("######################################################################")
                        logger.error("#                                                                    #")
                        logger.error("#       ERROR in calibrate: unknown array ID. Exiting script.        #")
                        logger.error("#                                                                    #")
                        logger.error("######################################################################")
                        logger.error("######################################################################\n")
                        raise SystemExit
                    
                    prepareCalibrations(QHflatsfilename, IRflatsfilename, arcsfilename, pinholesfilename, nsprepareInter, \
                        preparedPrefix, reducedPrefix, bpmfile, overwrite)

                    logger.info("####################################################################")
                    logger.info("#                                                                  #")
                    logger.info("#    STEP 2: Preparing all calibration frames (QHflats, IRflats    #")
                    logger.info("#            arcs, and pinholes) - COMPLETED                       #")
                    logger.info("#                                                                  #")
                    logger.info("####################################################################\n")

                #############################################################################
                ##  STEP 3: Create flat field images for QHflats and IR flats.             ##
                ##          Create the final flat by grouping order 3 of IRflats and       ## 
                ##          orders 4-18 of QHflats.                                        ##
                ##  Output: Flat Field image.                                              ##
                #############################################################################

                elif valindex == 3:
                    if manualMode:
                        a = raw_input("About to enter step 3: create flat field.")

                    makeFlat(preparedPrefix, reducedPrefix, QHflatsfilename, IRflatsfilename, QHflat, QHflat_bpm, \
                        IRflat, IRflat_bpm, masterflat, nsflatInter, overwrite)

                    logger.info("###################################################################")
                    logger.info("#                                                                 #")
                    logger.info("#      STEP 3: Create flat field (QHflat, IRflat, and the         #")
                    logger.info("#              final flat) - COMPLETED                            #")
                    logger.info("#                                                                 #")
                    logger.info("###################################################################\n")

                ########################################################################################
                ##  Step 4: Trace the spatial curvature and spectral distortion in the pinhole flat.  ##
                ##  Output: Pinhole flat for which the spatial curvature and S-distortion has been    ##
                ##          determined.                                                               ##
                ########################################################################################

                elif valindex == 4:
                    if manualMode:
                        a = raw_input("About to enter step 4: spatial curvature and spectral distortion.")

                    if 'LB_SXD' in calpath or 'LB_LXD' in calpath:
                        pinhole_coordlist = 'gnirs$data/pinholes-long-dense-north.lis'
                        pinholesnumber = 9
                    elif 'SB_SXD' in calpath:
                        pinhole_coordlist = 'gnirs$data/pinholes-short-dense-north.lis'
                        pinholesnumber = 6
                    else:
                        logger.error("#######################################################################")
                        logger.error("#######################################################################")
                        logger.error("#                                                                     #")
                        logger.error("#         ERROR in calibrate: unknown camera. Exiting script.         #")
                        logger.error("#                                                                     #")
                        logger.error("#######################################################################")
                        logger.error("#######################################################################\n")
                        raise SystemExit

                    makeSdistortion(nssdistInter, sdistrefimage, pinhole_coordlist, pinholesnumber, databaseDir, \
                        reducedPrefix, preparedPrefix, overwrite)
                
                    logger.info("####################################################################")
                    logger.info("#                                                                  #")
                    logger.info("#     Step 4: Spatial curvature and spectral distortion (trace     #")
                    logger.info("#             the spatial curvature and spectral distortion in     #") 
                    logger.info("#             the pinhole flat) - COMPLETED                        #")
                    logger.info("#                                                                  #")
                    logger.info("####################################################################\n")

                ############################################################################
                ##  STEP 5: Combine arc frames.                                           ##
                ##          Determine the wavelength solution and create the wavelength-  ##
                ##          calibrated arc image corrected for spatial distortion.        ##
                ##  OUTPUT: Combined and wavelength calibrated arc image.                 ##
                ############################################################################

                elif valindex == 5:
                    if manualMode:
                        a = raw_input("About to enter step 5: wavelength solution.")
                    
                    if '10' in calpath and '32' in calpath:
                        waveCal_coordlist = 'gnirs$data/lowresargon.dat'
                    elif '110' in calpath:
                        waveCal_coordlist = 'gnirs$data/argon.dat'
                    else:
                        logger.error("########################################################################")
                        logger.error("########################################################################")
                        logger.error("#                                                                      #")
                        logger.error("#         ERROR in calibrate: unknown grating. Exiting script.         #")
                        logger.error("#                                                                      #")
                        logger.error("########################################################################")
                        logger.error("########################################################################\n")
                        raise SystemExit

                    makeWaveCal(arcsfilename, preparedPrefix, reducedPrefix, combinedarc, databaseDir, fitcoordsPrefix, \
                        transformPrefix, waveCalibPrefix, nscombineInter, nsfitcoordsInter, nswavelengthInter, sdistrefimage, \
                        waveCal_coordlist, orders, nominal_wavelengths, advertised_accuracy_percent, overwrite)
                    
                    logger.info("####################################################################")
                    logger.info("#                                                                  #")
                    logger.info("#   STEP 5: Wavelength solution (Combine arc frames, determine     #")
                    logger.info("#           the wavelength solution, and create the wavelength     #")
                    logger.info("#           referenced arc image) - COMPLETED                      #")
                    logger.info("#                                                                  #")
                    logger.info("####################################################################\n")

                else:
                    logger.error("########################################################################")
                    logger.error("########################################################################")
                    logger.error("#                                                                      #")
                    logger.error("#  ERROR in calibrate: %d", valindex, " is not valid. Exiting script.  #")
                    logger.error("#                                                                      #")
                    logger.error("########################################################################")
                    logger.error("########################################################################\n")
                    raise SystemExit

                valindex += 1

            logger.info("###########################################################################")
            logger.info("#                                                                         #")
            logger.info("#             COMPLETE - Calibration reductions completed for             #")
            logger.info("#  %s", calpath                                                             )
            logger.info("#                                                                         #")
            logger.info("###########################################################################\n")
        
        else:
            logger.warning("######################################################################################")
            logger.warning("######################################################################################")
            logger.warning("#                                                                                    #")
            logger.warning("#    GNIRS baseline calibration turned off. Not reducing baseline calibrations in    #")
            logger.warning("#    %s", calpath                                                                      )
            logger.warning("#                                                                                    #")
            logger.warning("######################################################################################")
            logger.warning("######################################################################################\n")

    # Return to directory script was begun from.
    iraf.chdir(path)
        
    return

#####################################################################################
#                                        FUNCTIONS                                  #
#####################################################################################

def nofits(filename):
    """
    Remove extension '.fits' from the filename.
    """
    logger = log.getLogger('gnirsFluxCalibration.nofits')
    
    return filename.replace('.fits', '')

#---------------------------------------------------------------------------------------------------------------------#

def cleanNoise(inputlist, outputPrefix, overwrite):
    """
    Clean detectoer pattern noise in images.  
    
    TODO:  Currently (August 2019), this function does nit perform the cleaning.
    """
    logger = log.getLogger('gnirsBaselineCalibration.cleanNoise')

    oldfiles = glob.glob(outputPrefix + 'N*.fits')
    if len(oldfiles) > 0:
        if overwrite:
            logger.warning("Removing old %sN*.fits files.", outputPrefix)
            [os.remove(filename) for filename in oldfiles]
        else:
            logger.warning("Output exists and overwrite flag not set.")
            logger.warning("Skipping cleanir for the input list of images.\n")
            return
    
    pass

#---------------------------------------------------------------------------------------------------------------------#

def prepareCalibrations(QHflatsfilename, IRflatsfilename, arcsfilename, pinholesfilename, interactive, preparedPrefix, \
    reducedPrefix, bpmfile, overwrite):
    """
    Prepare calibration frames for further processing.

    Use NSPREPARE on all calibration frames (QHflats, IRflats, arcs, pinholes, and darks to update the raw data headers 
    and attach the mask definition file (MDF) as a binary table on all files. Note that dark frames will not have an 
    MDF attached by default. Instead, the appropriate MDF is added in NSREDUCE or NSFLAT to match the data being 
    reduced.

    Use NSREDUCE to cut the calibration frame spectra to the size specified by the MDF, placing different spectral
    orders in separate image extensions. Darks will not be used for further reductions after this point.
    """
    logger = log.getLogger('gnirsBaselineCalibration.prepareCalibrations')

    oldfiles = glob.glob(preparedPrefix + 'N*.fits') + glob.glob(reducedPrefix + preparedPrefix + 'N*.fits')
    if len(oldfiles) > 0:
        if overwrite:
            logger.warning('Removing old files: %sN*.fits and %s%sN*.fits files', preparedPrefix, reducedPrefix, preparedPrefix)
            [os.remove(filename) for filename in oldfiles] 
        else:
            logger.warning("Output exists and -overwrite not set.")
            logger.warning("Skipping nsprepare and nsreduce for all calibration frames.\n")
            return

    # Update all calibration frames with mdf offset value and generate variance and data quality extensions.
    iraf.nsprepare(
        inimages='@'+QHflatsfilename+',@'+IRflatsfilename+',@'+arcsfilename+',@'+pinholesfilename, rawpath='', 
        outimages='', outprefix=preparedPrefix, bpm=bpmfile, logfile=logger.root.handlers[0].baseFilename, 
        fl_vardq='yes', fl_cravg='no', crradius=0.0, fl_dark_mdf='no', fl_correct='no', fl_saturated='yes', 
        fl_nonlinear='yes', fl_checkwcs='yes', fl_forcewcs='yes', arraytable='gnirs$data/array.fits',
        configtable='gnirs$data/config.fits', specsec='[*,*]', offsetsec='none', pixscale='0.15', shiftimage='',
        shiftx='INDEF', shifty='INDEF', obstype='FLAT', fl_inter=interactive, verbose='yes', mode='al')

    # Cut all calibration frames according to the size specified by the MDFs.
    iraf.nsreduce(
        inimages=preparedPrefix+'//@'+QHflatsfilename+','+preparedPrefix+'//@'+IRflatsfilename+','+preparedPrefix+'//@'+arcsfilename+','+preparedPrefix+'//@'+pinholesfilename, 
        outimages='', outprefix=reducedPrefix, fl_cut='yes', section='', fl_corner='yes', fl_process_cut='yes', 
        fl_nsappwave='no', nsappwavedb='gnirs$data/nsappwave.fits', crval='INDEF', cdelt='INDEF', fl_dark='no', 
        darkimage='', fl_save_dark='no', fl_sky='no', skyimages='', skysection='', combtype='median', 
        rejtype='avsigclip', masktype='goodvalue', maskvalue=0.0, scale='none', zero='median', weight='none', 
        statsec='[*,*]', lthreshold='INDEF', hthreshold='INDEF', nlow=1, nhigh=1, nkeep=0, mclip='yes', lsigma=3.0, 
        hsigma=3.0, snoise='0.0', sigscale=0.1, pclip=-0.5, grow=0.0, skyrange='INDEF', nodsize=3.0, fl_flat='no',
        flatimage='', flatmin=0.0, fl_vardq='yes', logfile=logger.root.handlers[0].baseFilename, verbose='yes',
        debug='no', force='no', mode='al')

    return

#---------------------------------------------------------------------------------------------------------------------#

def makeFlat(preparedPrefix, reducedPrefix, QHflatsfilename, IRflatsfilename, QHflat, QHflat_bpm, IRflat, IRflat_bpm, \
    masterflat, nsflatInter, overwrite):
    """
    Make flat field and bad pixel masks.

    Use NSFLAT to generate a normalized flat field for the QHflats and IRflats (for each cross-dispersed order). A mask 
    (BPM) will also be generated by thresholding - this can be used to flag bad pixels in other data.

    Use FXCOPY followed by FXINSERT to produce the final flat by grouping order 3 of IRflats and orders 4-18 of 
    QHflats. The output from this task is used as the flatfield image for further reduction.

    TODO(Viraja):  Sometimes nsflat crashes with a fixpix or other, unknown error. In such a situation, tweaking the 
    lthresh parameter sometimes helps. XDGNIRS loops through a fixed list of lthresh values until it (hopefully) runs
    without an error in three trials after which it fails and exits. The nsflat function in this pipeline is currently
    not set to run through a loop; it simply uses the specified lthresh. However, it can be made to run through a loop
    of random lthresh values in a specified range until it runs without an error to avoid a system exit.
    """
    logger = log.getLogger('gnirsBaselineCalibration.makeFlat')

    # Generate normalized flat field images for QHflats and IRflats.
    if os.path.exists(QHflat):
        if overwrite:
            logger.warning('Removing old %s', QHflat)
            os.remove(QHflat)
            QHflat_flag = False
        else:
            logger.warning("Old %s exists and -overwrite not set - using existing output for further ", QHflat)
            logger.warning("reduction.")
            QHflat_flag = True
    else:
        QHflat_flag = False
    if os.path.exists(QHflat_bpm):
        if overwrite:
            logger.warning('Removing old %s', QHflat_bpm)
            os.remove(QHflat_bpm)
            QHflat_bpm_flag = False
        else:
            logger.warning("Old %s exists and -overwrite not set - using existing output for further ", QHflat_bpm)
            logger.warning("reduction.")
            QHflat_bpm_flag = True
    else:
        QHflat_bpm_flag = False
    if QHflat_flag and QHflat_bpm_flag:
        pass
    else:
        iraf.nsflat(lampson=reducedPrefix+preparedPrefix+'//@'+QHflatsfilename, darks='', flatfile=QHflat, darkfile='', 
            fl_corner='yes', fl_save_darks='no', flattitle='default', bpmtitle='default', bpmfile=QHflat_bpm, process="fit", 
            statsec='MDF', fitsec='MDF', thr_flo=0.35, thr_fup=4.0, thr_dlo=-20, thr_dup=100, fl_inter=nsflatInter, 
            fl_range='no', fl_fixbad='yes', fixvalue=1.0, function='spline3', order=5, normstat='midpt', 
            combtype='default', rejtype='ccdclip', masktype='goodvalue', maskvalue=0.0, scale='median', zero='none', 
            weight='none', lthreshold=50.0, hthreshold='INDEF', nlow=1, nhigh=1, nkeep=0, mclip='yes', lsigma=3.0, 
            hsigma=3.0, snoise='0.0', sigscale=0.1, pclip=-0.5, grow=0.0, box_width=20, box_length=1, trace='', 
            traceproc='none', threshold=100.0, aptable='gnirs$data/apertures.fits', database='', apsum=10, tr_step=10,
            tr_nlost=3, tr_function='legendre', tr_order=5, tr_naver=1, tr_niter=0, tr_lowrej=3.0, tr_highrej=3.0, 
            tr_grow=0.0, ap_lower=-30, ap_upper=30, fl_vardq='yes', logfile=logger.root.handlers[0].baseFilename, 
            verbose='yes', mode='al')

    if os.path.exists(IRflat):
        if overwrite:
            logger.warning('Removing old %s', IRflat)
            os.remove(IRflat)
            IRflat_flag = False
        else:
            logger.warning("Old %s exists and -overwrite not set - using existing output for further ", IRflat)
            logger.warning("reduction.")
            IRflat_flag = True
    else:
        IRflat_flag = False
    if os.path.exists(IRflat_bpm):
        if overwrite:
            logger.warning('Removing old %s', IRflat_bpm)
            os.remove(IRflat_bpm)
            IRflat_bpm_flag = False
        else:
            logger.warning("Old %s exists and -overwrite not set - using existing output for further ", IRflat_bpm)
            logger.warning("reduction.")
            IRflat_bpm_flag = True
    else:
        IRflat_bpm_flag = False
    if IRflat_flag and IRflat_bpm_flag:
        pass
    else:
        iraf.nsflat(lampson=reducedPrefix+preparedPrefix+'//@'+IRflatsfilename, darks='', flatfile=IRflat, darkfile='', 
            fl_corner='yes', fl_save_darks='no', flattitle='default', bpmtitle='default', bpmfile=IRflat_bpm, process="fit", 
            statsec='MDF', fitsec='MDF', thr_flo=0.35, thr_fup=1.5, thr_dlo=-20, thr_dup=100, fl_inter=nsflatInter, 
            fl_range='no', fl_fixbad='yes', fixvalue=1.0, function='spline3', order=10, normstat='midpt', 
            combtype='default', rejtype='ccdclip', masktype='goodvalue', maskvalue=0.0, scale='none', zero='none', 
            weight='none', lthreshold=50.0, hthreshold='INDEF', nlow=1, nhigh=1, nkeep=0, mclip='yes', lsigma=3.0, 
            hsigma=3.0, snoise='0.0', sigscale=0.1, pclip=-0.5, grow=0.0, box_width=20, box_length=1, trace='', 
            traceproc='none', threshold=100.0, aptable='gnirs$data/apertures.fits', database='', apsum=10, tr_step=10,
            tr_nlost=3, tr_function='legendre', tr_order=5, tr_naver=1, tr_niter=0, tr_lowrej=3.0, tr_highrej=3.0, 
            tr_grow=0.0, ap_lower=-30, ap_upper=30, fl_vardq='yes', logfile=logger.root.handlers[0].baseFilename, 
            verbose='yes', mode='al')

    # Group order 3 of IRflats and orders 4-18 of QHflats to create the final flat field image. Output flat field image 
    # will be "masterflat.fits".
    if os.path.exists(masterflat):
        if overwrite:
            logger.warning('Removing old %s', masterflat)
            os.remove(masterflat)
            iraf.fxcopy(input=IRflat, output=masterflat, group="0-3", new_file='yes', verbose='no', mode='ql')
            iraf.fxinsert(input=QHflat, output=masterflat+'[3]', groups="4-18", verbose='no', mode='ql')
        else:
            logger.warning("Old %s exists", masterflat, " and -overwrite not set - skipping fxcopy and fxinsert to ")
            logger.warning("create the masterflat.")
    else:
        iraf.fxcopy(input=IRflat, output=masterflat, group="0-3", new_file='yes', verbose='no', mode='ql')
        iraf.fxinsert(input=QHflat, output=masterflat+'[3]', groups="4-18", verbose='no', mode='ql')

#---------------------------------------------------------------------------------------------------------------------#

def makeSdistortion(nssdistInter, sdistrefimage, pinhole_coordlist, pinholesnumber, databaseDir, reducedPrefix, \
    preparedPrefix, overwrite):
    """
    Establish Spatial distortion calibration.

    NSSDIST uses the information in the pinhole calibration images to calibrate the spatial distorion of the GNIRS 
    field. The pinhole frame is a dispersed flat field image with a slit-mask in the field so that the illumination on 
    GNIRS is in a pattern of 6 different holes that are stacked in the y-dimension on the field. Proper alignment of
    the slit across the pattern can be used for spatial rectification of the on-sky science data. The spatial solution
    determined by NSSSDIST is linked to the science data in NSFITCOORDS.
    """
    logger = log.getLogger('gnirsBaselineCalibration.makeSdistortion')
   
    oldfiles = glob.glob('./' + databaseDir + '/id' + reducedPrefix + preparedPrefix + '*')
    if len(oldfiles) > 0:
        if overwrite:
            logger.warning('Removing old /%s/id%s%s* files.', databaseDir, reducedPrefix, preparedPrefix)
            [os.remove(filename) for filename in oldfiles]
        else:
            logger.warning("Output exists and overwrite flag not set.")
            logger.warning("Skipping the spatial distortion calculation and check for pinholes.\n")
            return
        
    iraf.nssdist(inimages=sdistrefimage, outsuffix='_sdist', pixscale=1.0, dispaxis=1, database=databaseDir, \
        firstcoord=0.0, coordlist=pinhole_coordlist, aptable='gnirs$data/apertures.fits', fl_inter=nssdistInter, \
        fl_dbwrite='yes', section='default', nsum=30, ftype='emission', fwidth=10.0, cradius=10.0, \
        threshold=1000.0, minsep=5.0, match=-6.0, function="legendre", order=5, sample='', niterate=3, \
        low_reject=5.0, high_reject=5.0, grow=0.0, refit='yes', step=10, trace='no', nlost=0, aiddebug='', \
        logfile=logger.root.handlers[0].baseFilename, verbose='no', debug='no', force='no', mode='al')

    # Check that the right number of pinholes have been identified
    logger.info("Checking if right number of pinholes identified.\n")
    idrnfiles = sorted(glob.glob('./database/idrn*'))
    for i in range(len(idrnfiles)):
        idrnfile = open(idrnfiles[i], "r")
        # Read up to the first occurrence of "features" in the file
        for line in idrnfile:
            if "features" in line:
                if line.split()[1] != str(pinholesnumber):
                    logger.warning("Expected %d pinholes to be detected by nssdist, but found ", pinholesnumber)
                    logger.warning("%s pinholes in extension %d. This can cause problems. ", line.split()[1], i)
                    logger.warning("Please check the transformed data files (ttf*.fits) later and look for ")
                    logger.warning("inter-order offsets in 'orders.pdf' file created by gnirsCombineOrdersXD.py.")
                    break
                else:
                    logger.info("Right number of pinholes detected by nssdist in extension %d", i)
                    break
        idrnfile.close()
    logger.info("Number of pinholes check complete.\n")

#---------------------------------------------------------------------------------------------------------------------#

def makeWaveCal(arcsfilename, preparedPrefix, reducedPrefix, combinedarc, databaseDir, fitcoordsPrefix, transformPrefix, \
    waveCalibPrefix, nscombineInter, nsfitcoordsInter, nswavelengthInter, sdistrefimage, waveCal_coordlist, orders, \
    nominal_wavelengths, advertised_accuracy_percent, overwrite):
    """
    Determine the wavelength solution of the combined arc.

    Uses NSWAVELENGTH to calibrate arcs (after cutting and optionally applying a flatfield with NSREDUCE previously).

    Note that better RMS fits can be obtained by running the wavelength calibration interactively and identifying all 
    of the lines manually. Tedious, but will give more accurate results than the automatic mode (i.e., fl_inter-).
    """
    logger = log.getLogger('gnirsBaselineCalibration.makeWaveCal')
    
    # Combine arc frames.
    if os.path.exists(combinedarc):
        if overwrite:
            logger.warning('Removing old %s', combinedarc)
            os.remove(combinedarc)
            iraf.nscombine(inimages=reducedPrefix+preparedPrefix+'//@'+arcsfilename, tolerance=0.5, output=combinedarc,
                output_suffix='_comb', bpm='', dispaxis=1, pixscale=1.0, fl_cross='no', fl_keepshift='no', fl_shiftint='yes',
                interptype='linear', boundary='nearest', constant=0.0, combtype='average', rejtype='sigclip',
                masktype='goodvalue', maskvalue=0.0, statsec='[*,*]', scale='none', zero='none', weight='none',
                lthreshold='INDEF', hthreshold='INDEF', nlow=1, nhigh=1, nkeep=0, mclip='yes', lsigma=5.0, hsigma=5.0,
                ron=0.0, gain=1.0, snoise='0.0', sigscale=0.1, pclip=-0.5, grow=0.0, nrejfile='', fl_vardq='yes', 
                fl_inter=nscombineInter, logfile=logger.root.handlers[0].baseFilename, verbose='yes', debug='no',
                force='no', mode='al')
        else:
            logger.warning("Output file exists and overwrite flag not set.")
            logger.warning("Skipping combining arcs. Using the existing output for further processing.\n")
    else:
        iraf.nscombine(inimages=reducedPrefix+preparedPrefix+'//@'+arcsfilename, tolerance=0.5, output=combinedarc, 
            output_suffix='_comb', bpm='', dispaxis=1, pixscale=1.0, fl_cross='no', fl_keepshift='no', fl_shiftint='yes', 
            interptype='linear', boundary='nearest', constant=0.0, combtype='average', rejtype='sigclip', masktype='goodvalue',
            maskvalue=0.0, statsec='[*,*]', scale='none', zero='none', weight='none', lthreshold='INDEF', 
            hthreshold='INDEF', nlow=1, nhigh=1, nkeep=0, mclip='yes', lsigma=5.0, hsigma=5.0, ron=0.0, gain=1.0, 
            snoise='0.0', sigscale=0.1, pclip=-0.5, grow=0.0, nrejfile='', fl_vardq='yes', fl_inter=nscombineInter, 
            logfile=logger.root.handlers[0].baseFilename, verbose='yes', debug='no', force='no', mode='al')

    oldfiles_transformed = glob.glob('./*' + fitcoordsPrefix + nofits(combinedarc) + '*')
    oldfiles_waveCal = glob.glob('./' + databaseDir + '/id' + waveCalibPrefix + transformPrefix + fitcoordsPrefix + '*')
    oldfiles_sdist = glob.glob('./' + databaseDir + '/*_sdist')
    oldfiles_lamp = glob.glob('./' + databaseDir + '/*_lamp')
    oldfiles_arcorderslist = glob.glob('./arcorders*')
    oldfiles_combined = glob.glob('./arc_calibrated*')
    oldfiles = oldfiles_transformed + oldfiles_waveCal + oldfiles_sdist + oldfiles_lamp + oldfiles_arcorderslist + \
        oldfiles_combined
    if len(oldfiles) > 0:
        if overwrite:
            logger.warning("Removing old /*f%s*, /arcorders.list, /database/idwtf*, /database/*_sdist", combinedarc)
            logger.info("/database/*_lamp, and /arc_calibrated.fits files.")
            [os.remove(filename) for filename in oldfiles]
        else:
            logger.warning("Output exidts and overwrite flag not set.")
            logger.warning("Skipping wavelength calibration and spatial distortion correction of arcs.\n")
            return

    logger.info("Running nsfitcoords and nstransform on the combined arc to spatially rectify it before running ") 
    logger.info("nswavelength.")
    iraf.nsfitcoords(inimages=combinedarc, outspectra='', outprefix=fitcoordsPrefix, lamptransf='', 
        sdisttransf=sdistrefimage, dispaxis=1, database=databaseDir, fl_inter=nsfitcoordsInter, fl_align='no', 
        function='chebyshev', lxorder=2, lyorder=4, sxorder=4, syorder=4, pixscale=1.0, 
        logfile=logger.root.handlers[0].baseFilename, verbose='yes', debug='no', force='no', mode='al')
    iraf.nstransform(inimages='f'+combinedarc, outspectra='', outprefix='t', dispaxis=1, database=databaseDir, 
        fl_stripe='no', interptype='poly3', xlog='no', ylog='no', pixscale=1.0, 
        logfile=logger.root.handlers[0].baseFilename, verbose='yes', debug='no', mode='al')
        
    logger.info("The arc lines might still be a bit tilted because of the detector rotation. Running ")
    logger.info("nswavelength on the transformed arc with fl_median-.")
    iraf.nswavelength(lampspectra=transformPrefix+fitcoordsPrefix+combinedarc, outspectra='', 
        outprefix=waveCalibPrefix, crval='INDEF', cdelt='INDEF', crpix='INDEF', dispaxis=2, database=databaseDir, 
        coordlist=waveCal_coordlist, fl_inter=nswavelengthInter, nsappwavedb='gnirs$data/nsappwave.fits', 
        fl_median='no', sdist='', sdorder=4, xorder=2, yorder=2, aptable='gnirs$data/apertures.fits', 
        section='auto', nsum=10, ftype='emission', fwidth=5.0, cradius=5.0, threshold=300.0, minsep=2.0, 
        match=-6.0, function='chebyshev', order=4, sample='*', niterate=10, low_reject=3.0, high_reject=3.0, 
        grow=0.0, refit='yes', step=2, trace='no', nlost=10, fl_overwrite='yes', aiddebug='', fmatch=0.2, 
        nfound=6, sigma=0.05, rms=0.1, logfile=logger.root.handlers[0].baseFilename, verbose='yes', 
        debug='no', mode='al')
        
    logger.info("Calling nsfitcoords to produce the combined arc with horizontal lines and then nstransform on ")
    logger.info("the transformed arc using the output from nswavelength for the 'lamptrans' parameter.")
    iraf.nsfitcoords(inimages=transformPrefix+fitcoordsPrefix+combinedarc, outspectra='', outprefix=fitcoordsPrefix, 
        lamptrans=waveCalibPrefix+transformPrefix+fitcoordsPrefix+combinedarc, sdisttransf='', dispaxis=1, 
        database=databaseDir, fl_inter=nsfitcoordsInter, fl_align='no', function='chebyshev', lxorder=2, lyorder=4, 
        sxorder=4, syorder=4, pixscale=1.0, logfile=logger.root.handlers[0].baseFilename, verbose='yes', 
        debug='no', force='no', mode='al')
    iraf.nstransform(inimages=fitcoordsPrefix+transformPrefix+fitcoordsPrefix+combinedarc, outspectra='', 
        outprefix=transformPrefix, dispaxis=1, database=databaseDir, fl_stripe='no', interptype='poly3', xlog='no', ylog='no', 
        pixscale=1.0, logfile=logger.root.handlers[0].baseFilename, verbose='no', debug='no', mode='al')

    # Check if wavelength calibration looks reasonable by extracting a single column approximately down the middle
    # of each order, then combining orders
    logger.info("Creating a wavelength calibrated arc spectrum.")
    ## TODO(Viraja):  Check with Andy if it is a good idea to randomize the column selection, within a fixed range
    columns = [88,77,65,54,53,92]  
    for i in range(len(orders)):
        extension = i+1

        try:
            iraf.imcopy(input=transformPrefix+fitcoordsPrefix+transformPrefix+fitcoordsPrefix+combinedarc+'[SCI,'+str(extension)+']['+str(columns[i])+',*]',
                output=transformPrefix+fitcoordsPrefix+transformPrefix+fitcoordsPrefix+nofits(combinedarc)+'_order'+str(extension)+'.fits', 
                verbose='yes', mode='ql')
        except(TypeError,iraf.IrafError) as arcCalibration_error:
            logger.error(arcCalibration_error)
            logger.error("A problem was encountered in making the wavelength solution. First, check that the raw ")
            logger.error("and the reduced arcs look sensible. Second, check that the spectral orders are in the ")
            logger.error("same place in the array (in the x direction) in all the raw files to within a few ")
            logger.error("pixels. Third, try running nssdist, nsfitcoords, and nswavelength interactively by ")
            logger.error("setting nssdistInter, nsfitcoordsInter, and nswavelengthInter, respectively. Exiting ")
            logger.error("script.\n")
            sys.exit(0)
    with open('./arcorders.list', 'a+') as f:
        for filename in sorted(glob.glob('./'+transformPrefix+fitcoordsPrefix+transformPrefix+fitcoordsPrefix+nofits(combinedarc)+'_order*.fits')):
            filename = filename[filename.rfind('/')+1:]
            if filename not in f.read().split('\n'):
                f.write(filename + '\n')
    iraf.odcombine(input='@arcorders.list//[SCI,1]', output='arc_calibrated.fits', headers='', bpmasks='', rejmask='', 
        nrejmasks='', expmasks='', sigma='', logfile=logger.root.handlers[0].baseFilename, apertures='', 
        group='all', first='no', w1='INDEF', w2='INDEF', dw='INDEF', nw='INDEF', log='no', combine='average', 
        reject='none', outtype='real', outlimits='', smaskformat='bpmspectrum', smasktype='none', smaskvalue=0.0, 
        blank=0.0, scale='none', zero='none', weight='none', statsec='', expname='', lthreshold='INDEF', 
        hthreshold='INDEF', nlow=1, nhigh=1, nkeep=1, mclip='yes', lsigma=3.0, hsigma=3.0, rdnoise='0.0', 
        gain='1.0', snoise='0.0', sigscale=0.1, pclip=-0.5, grow=0.0, offsets='physical', masktype='none', 
        maskvalue=0.0, mode='al')

    # Check if the starting and ending wavelengths of the orders are reasonable. As of January 2016, we advertised, 
    # that "wavelength settings ... are accurate to better than 5 percent of the wavelength coverage." (see, note a 
    # at the bottom of the table here: http://www.gemini.edu/sciops/instruments/gnirs/spectroscopy). 
    # Take the nominal starting and ending wavelengths from the OT, and check if the ones from the wavelength 
    # calibration are the same to within the advertised tolerance.
    logger.info("Checking if the starting and the ending wavelengths of the wavelength solution are reasonable.\n")
    for i in range(len(orders)):
        extension = i+1

        waveStart = iraf.hselect(images=transformPrefix+fitcoordsPrefix+transformPrefix+fitcoordsPrefix+combinedarc[:combinedarc.rfind('.')]+'[SCI,'+str(extension)+']',
            fields='CRVAL2', expr='yes', missing='INDEF', Stdout=1)
        waveStart = float(waveStart[0].replace("'",""))
        waveDelt = iraf.hselect(images=transformPrefix+fitcoordsPrefix+transformPrefix+fitcoordsPrefix+combinedarc[:combinedarc.rfind('.')]+'[SCI,'+str(extension)+']',
            fields='CDELT2', expr='yes', missing='INDEF', Stdout=1)
        waveDelt = float(waveDelt[0].replace("'",""))
        waveEnd = waveStart + (1022 * waveDelt)
        advertised_accuracy = (nominal_wavelengths[extension][1] - nominal_wavelengths[extension][0]) * \
            advertised_accuracy_percent/100
        if abs(waveStart - nominal_wavelengths[extension][0]) > advertised_accuracy:
            logger.warning("Starting wavelength for extension %d > %f percent", extension, advertised_accuracy_percent)
            logger.warning("away from the expected value (actual %fum vs. expected", waveStart)
            logger.warning("%fum+/-%fum.", nominal_wavelengths[extension][0], advertised_accuracy)
        else:
            logger.info("Starting wavelength for extension %d < %f percent", extension, advertised_accuracy_percent)
            logger.info("away from the expected value (actual %fum vs. expected ", waveStart)
            logger.info("%fum+/-%fum.", + nominal_wavelengths[extension][0], advertised_accuracy)
        if abs(waveEnd - nominal_wavelengths[extension][1]) > advertised_accuracy:
            logger.warning("Ending wavelength for extension %d > %f percent", extension, advertised_accuracy_percent)
            logger.warning("away from the expected value (actual %fum vs. expected ", waveEnd)
            logger.warning("%fum+/-%fum.", nominal_wavelengths[extension][1], advertised_accuracy)
        else:
            logger.info("Ending wavelength for extension %d < %f percent", extension, advertised_accuracy_percent)
            logger.info("away from the expected value (actual %fum vs. expected ", waveEnd)
            logger.info("%fum+/-%fum.", nominal_wavelengths[extension][1], advertised_accuracy)
    logger.info("Starting and the ending wavelengths of the wavelength solution check complete.\n")
            
#---------------------------------------------------------------------------------------------------------------------#

if __name__ == '__main__':
    log.configure('gnirs.log', filelevel='INFO', screenlevel='DEBUG')
    start('gnirs.cfg')
